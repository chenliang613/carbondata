# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements.  See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.
# The ASF licenses this file to You under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with
# the License.  You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import division, print_function

import argparse

import jnius_config

import torch
import torch.nn.functional as F
import torch.optim as optim
from torchvision import transforms

from pycarbon.reader import make_reader
from pycarbon.tests.mnist.dataset_with_unischema import DEFAULT_MNIST_DATA_PATH
from pycarbon.tests import DEFAULT_CARBONSDK_PATH

from petastorm.pytorch import DataLoader
from petastorm import TransformSpec
from examples.mnist.pytorch_example import Net

def train(model, device, train_loader, log_interval, optimizer, epoch):
  model.train()
  for batch_idx, row in enumerate(train_loader):
    data, target = row['image'].to(device), row['digit'].to(device)
    optimizer.zero_grad()
    output = model(data)
    loss = F.nll_loss(output, target)
    loss.backward()
    optimizer.step()
    if batch_idx % log_interval == 0:
      print('Train Epoch: {} [{}]\tLoss: {:.6f}'.format(
        epoch, batch_idx * len(data), loss.item()))


def evaluation(model, device, test_loader):
  model.eval()
  test_loss = 0
  correct = 0
  count = 0
  with torch.no_grad():
    for row in test_loader:
      data, target = row['image'].to(device), row['digit'].to(device)
      output = model(data)
      test_loss += F.nll_loss(output, target, reduction='sum').item()  # sum up batch loss
      pred = output.max(1, keepdim=True)[1]  # get the index of the max log-probability
      correct += pred.eq(target.view_as(pred)).sum().item()
      count += data.shape[0]

  test_loss /= count
  print('\nTest set: Average loss: {:.4f}, Accuracy: {}/{} ({:.0f}%)\n'.format(
    test_loss, correct, count, 100. * correct / count))


def _transform_row(mnist_row):
  # For this example, the images are stored as simpler ndarray (28,28), but the
  # training network expects 3-dim images, hence the additional lambda transform.
  transform = transforms.Compose([
    transforms.Lambda(lambda nd: nd.reshape(28, 28, 1)),
    transforms.ToTensor(),
    transforms.Normalize((0.1307,), (0.3081,))
  ])
  # In addition, the petastorm pytorch DataLoader does not distinguish the notion of
  # data or target transform, but that actually gives the user more flexibility
  # to make the desired partial transform, as shown here.
  result_row = {
    'image': transform(mnist_row['image']),
    'digit': mnist_row['digit']
  }

  return result_row


def main():
  # Training settings
  parser = argparse.ArgumentParser(description='Pycarbon MNIST Example')
  default_dataset_url = 'file://{}'.format(DEFAULT_MNIST_DATA_PATH)
  parser.add_argument('--dataset-url', type=str,
                      default=default_dataset_url, metavar='S',
                      help='hdfs:// or file:/// URL to the MNIST pycarbon dataset '
                           '(default: %s)' % default_dataset_url)
  parser.add_argument('--batch-size', type=int, default=64, metavar='N',
                      help='input batch size for training (default: 64)')
  parser.add_argument('--test-batch-size', type=int, default=1000, metavar='N',
                      help='input batch size for testing (default: 1000)')
  parser.add_argument('--epochs', type=int, default=10, metavar='N',
                      help='number of epochs to train (default: 10)')
  parser.add_argument('--all-epochs', action='store_true', default=False,
                      help='train all epochs before testing accuracy/loss')
  parser.add_argument('--lr', type=float, default=0.01, metavar='LR',
                      help='learning rate (default: 0.01)')
  parser.add_argument('--momentum', type=float, default=0.5, metavar='M',
                      help='SGD momentum (default: 0.5)')
  parser.add_argument('--no-cuda', action='store_true', default=False,
                      help='disables CUDA training')
  parser.add_argument('--seed', type=int, default=1, metavar='S',
                      help='random seed (default: 1)')
  parser.add_argument('--log-interval', type=int, default=10, metavar='N',
                      help='how many batches to wait before logging training status')
  parser.add_argument('--carbon-sdk-path', type=str, default=DEFAULT_CARBONSDK_PATH,
                      help='carbon sdk path')
  args = parser.parse_args()
  use_cuda = not args.no_cuda and torch.cuda.is_available()

  jnius_config.set_classpath(args.carbon_sdk_path)

  torch.manual_seed(args.seed)

  device = torch.device('cuda' if use_cuda else 'cpu')

  model = Net().to(device)
  optimizer = optim.SGD(model.parameters(), lr=args.lr, momentum=args.momentum)

  # Configure loop and Reader epoch for illustrative purposes.
  # Typical training usage would use the `all_epochs` approach.
  #
  if args.all_epochs:
    # Run training across all the epochs before testing for accuracy
    loop_epochs = 1
    reader_epochs = args.epochs
  else:
    # Test training accuracy after each epoch
    loop_epochs = args.epochs
    reader_epochs = 1

  transform = TransformSpec(_transform_row, removed_fields=['idx'])

  # Instantiate each pycarbon Reader with a single thread, shuffle enabled, and appropriate epoch setting
  for epoch in range(1, loop_epochs + 1):
    with DataLoader(make_reader('{}/train'.format(args.dataset_url), num_epochs=reader_epochs,
                                       transform_spec=transform, is_batch=False),
                    batch_size=args.batch_size) as train_loader:
      train(model, device, train_loader, args.log_interval, optimizer, epoch)

    with DataLoader(make_reader('{}/test'.format(args.dataset_url), num_epochs=reader_epochs,
                                       transform_spec=transform, is_batch=False),
                    batch_size=args.test_batch_size) as test_loader:
      evaluation(model, device, test_loader)


if __name__ == '__main__':
  main()
