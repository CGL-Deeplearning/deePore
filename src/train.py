import argparse
import os
import sys
from PIL import Image, ImageOps
import numpy as np
import torch
import pandas as pd
from torch.utils.data import Dataset, DataLoader
from torchvision import transforms, utils
from torch.autograd import Variable
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from modules.model import Model
from modules.dataset import PileupDataset, TextColor
import random


def validate(data_file, batch_size, gpu_mode, trained_model, seq_len=1):
    transformations = transforms.Compose([transforms.ToTensor()])

    validation_data = PileupDataset(data_file, transformations)
    validation_loader = DataLoader(validation_data,
                                   batch_size=batch_size,
                                   shuffle=True,
                                   num_workers=16,
                                   pin_memory=gpu_mode
                                   )
    sys.stderr.write(TextColor.PURPLE + 'Data loading finished\n' + TextColor.END)

    model = trained_model.eval()
    if gpu_mode:
        model = model.cuda()

    # Loss and Optimizer
    criterion = nn.CrossEntropyLoss()

    # Train the Model
    sys.stderr.write(TextColor.PURPLE + 'Validation starting\n' + TextColor.END)
    total_loss = 0
    total_images = 0

    for i, (images, labels) in enumerate(validation_loader):
        hidden = model.init_hidden(images.size(0))
        if gpu_mode is True and images.size(0) % 8 != 0:
            continue

        images = Variable(images, volatile=True)
        labels = Variable(labels, volatile=True)
        if gpu_mode:
            images = images.cuda()
            labels = labels.cuda()

        for row in range(0, images.size(2), 1):
            # segmentation of image. Currently using 1xCoverage
            if row + seq_len > images.size(2):
                continue

            x = images[:, :, row:row + seq_len, :]
            y = labels[:, row:row + seq_len]

            total_variation = torch.sum(y).data[0]

            if total_variation == 0 and random.uniform(0, 1) * 100 > 5:
                continue
            elif random.uniform(0, 1) < total_variation / batch_size < 0.02:
                continue



            # Forward + Backward + Optimize
            outputs = model(x, hidden)
            hidden = repackage_hidden(hidden)
            # outputs = outputs.view(1, outputs.size(0), -1)
            loss = criterion(outputs.contiguous().view(-1, 3), y.contiguous().view(-1))

            # loss count
            total_images += batch_size
            total_loss += loss.data[0]

    print('Validation Loss: ' + str(total_loss/total_images))
    sys.stderr.write('Validation Loss: ' + str(total_loss/total_images) + "\n")


def get_window(index, window_size, length):
    if index - window_size < 0:
        return 0, index + window_size + (window_size-index)
    elif index + window_size >= length:
        return index - window_size - (window_size - (length - index)), length
    return index - window_size, index + window_size


def repackage_hidden(h):
    """Wraps hidden states in new Variables, to detach them from their history."""
    if type(h) == Variable:
        return Variable(h.data)
    else:
        return tuple(repackage_hidden(v) for v in h)


def train(train_file, validation_file, batch_size, epoch_limit, file_name, gpu_mode):

    transformations = transforms.Compose([transforms.ToTensor()])

    sys.stderr.write(TextColor.PURPLE + 'Loading data\n' + TextColor.END)
    train_data_set = PileupDataset(train_file, transformations)
    train_loader = DataLoader(train_data_set,
                              batch_size=batch_size,
                              shuffle=True,
                              num_workers=16,
                              pin_memory=gpu_mode
                              )
    sys.stderr.write(TextColor.PURPLE + 'Data loading finished\n' + TextColor.END)

    model = Model()
    if gpu_mode:
        model = torch.nn.DataParallel(model).cuda()

    # Loss and Optimizer
    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.SGD(model.parameters(), lr=0.001)

    # Train the Model
    sys.stderr.write(TextColor.PURPLE + 'Training starting\n' + TextColor.END)
    seq_len = 3
    iteration_jump = 1
    for epoch in range(epoch_limit):
        total_loss = 0
        total_images = 0
        total_could_be = 0
        for i, (images, labels) in enumerate(train_loader):
            hidden = model.init_hidden(images.size(0))
            # if batch size not distributable among all GPUs then skip
            if gpu_mode is True and images.size(0) % 8 != 0:
                continue

            images = Variable(images, requires_grad=False)
            labels = Variable(labels, requires_grad=False)
            if gpu_mode:
                images = images.cuda()
                labels = labels.cuda()

            for row in range(0, images.size(2), iteration_jump):
                # segmentation of image. Currently using seq_len
                if row+seq_len > images.size(2):
                    continue

                x = images[:, :, row:row+seq_len, :]
                y = labels[:, row:row + seq_len]

                total_variation = torch.sum(y).data[0]
                total_could_be += batch_size
                # print(total_variation)

                if total_variation == 0 and random.uniform(0, 1)*100 > 5:
                    continue
                elif random.uniform(0, 1) < total_variation/batch_size < 0.02:
                    continue

                # print(x)
                # print(y)
                # exit()

                # Forward + Backward + Optimize
                optimizer.zero_grad()
                outputs = model(x, hidden)
                hidden = repackage_hidden(hidden)
                # print('Label: ', y.data[0])
                # print('Values:', outputs.data[0])
                # print(y.contiguous().view(-1))
                # exit()
                # outputs = outputs.view(1, outputs.size(0), -1) required for CTCLoss

                loss = criterion(outputs.contiguous().view(-1, 3), y.contiguous().view(-1))
                # print(outputs.contiguous().view(-1, 3).size())
                # print(y.contiguous().view(-1).size())
                # exit()
                loss.backward()
                optimizer.step()

                # loss count
                total_images += batch_size
                total_loss += loss.data[0]

            sys.stderr.write(TextColor.BLUE + "EPOCH: " + str(epoch) + " Batches done: " + str(i+1))
            sys.stderr.write(" Loss: " + str(total_loss/total_images) + "\n" + TextColor.END)
            print(str(epoch) + "\t" + str(i + 1) + "\t" + str(total_loss/total_images))

        # After each epoch do validation
        validate(validation_file, batch_size, gpu_mode, model, seq_len)
        sys.stderr.write(TextColor.YELLOW + 'Could be: ' + str(total_could_be) + ' Chosen: ' + str(total_images) + "\n" + TextColor.END)
        sys.stderr.write(TextColor.YELLOW + 'EPOCH: ' + str(epoch))
        sys.stderr.write(' Loss: ' + str(total_loss/total_images) + "\n" + TextColor.END)
        torch.save(model, file_name + '_checkpoint_' + str(epoch) + '.pkl')
        torch.save(model.state_dict(), file_name + '_checkpoint_' + str(epoch) + '-params' + '.pkl')

    sys.stderr.write(TextColor.PURPLE + 'Finished training\n' + TextColor.END)
    torch.save(model, file_name+'_final.pkl')

    sys.stderr.write(TextColor.PURPLE + 'Model saved as:' + file_name + '.pkl\n' + TextColor.END)
    torch.save(model.state_dict(), file_name+'_final_params'+'.pkl')

    sys.stderr.write(TextColor.PURPLE + 'Model parameters saved as:' + file_name + '-params.pkl\n' + TextColor.END)

if __name__ == '__main__':
    '''
    Processes arguments and performs tasks to generate the pileup.
    '''
    parser = argparse.ArgumentParser()
    parser.register("type", "bool", lambda v: v.lower() == "true")
    parser.add_argument(
        "--train_file",
        type=str,
        required=True,
        help="Training data description csv file."
    )
    parser.add_argument(
        "--validation_file",
        type=str,
        required=True,
        help="Training data description csv file."
    )
    parser.add_argument(
        "--batch_size",
        type=int,
        required=False,
        default=100,
        help="Batch size for training, default is 100."
    )
    parser.add_argument(
        "--epoch_size",
        type=int,
        required=False,
        default=10,
        help="Epoch size for training iteration."
    )
    parser.add_argument(
        "--model_out",
        type=str,
        required=False,
        default='./model',
        help="Path and file_name to save model, default is ./model"
    )
    parser.add_argument(
        "--gpu_mode",
        type=bool,
        default=False,
        help="If true then cuda is on."
    )
    FLAGS, unparsed = parser.parse_known_args()

    train(FLAGS.train_file, FLAGS.validation_file, FLAGS.batch_size, FLAGS.epoch_size, FLAGS.model_out, FLAGS.gpu_mode)


