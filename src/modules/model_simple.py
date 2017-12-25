import torch
import torch.nn as nn
import torch.nn.functional as F
import math


# CNN Model (2 conv layer)
class Model(nn.Module):
    def __init__(self, inChannel, coverageDepth, classN, window_size, leak_value):
        super(Model, self).__init__()
        self.inChannel = inChannel
        self.coverageDepth = coverageDepth
        self.classN = classN
        self.leak_value = leak_value
        self.seq_len = window_size
        self.outChannels = [self.inChannel, 40, 80, 160, 320, 640]
        # -----CNN----- #
        self.identity1 = nn.Sequential(
            nn.Conv2d(self.outChannels[0], self.outChannels[1], (1, 1), groups=self.outChannels[0],
                      bias=False, stride=(1, 1)),
        )
        self.cell1 = nn.Sequential(
            nn.Conv2d(self.outChannels[0], self.outChannels[1], (1, 3), groups=self.outChannels[0],
                      padding=(0, 1), bias=False, stride=(1, 1)),
            nn.BatchNorm2d(self.outChannels[1]),
            nn.ReLU(),
            nn.Conv2d(self.outChannels[1], self.outChannels[1], (3, 3), groups=int(self.outChannels[1]/self.outChannels[1]),
                      padding=(0, 1), bias=False, stride=(1, 1)),
        )

        self.identity2 = nn.Sequential(
            nn.Conv2d(self.outChannels[1], self.outChannels[2], (1, 1),# groups=4,
                      bias=False, stride=(1, 1))
        )
        self.cell2 = nn.Sequential(
            nn.Conv2d(self.outChannels[1], self.outChannels[2], (1, 3),# groups=4,
                      padding=(0,1), bias=False, stride=(1, 1)),
            nn.BatchNorm2d(self.outChannels[2]),
            nn.ReLU(),
            nn.Conv2d(self.outChannels[2], self.outChannels[2], (3, 3),# groups=8,
                      padding=(1, 1), bias=False, stride=(1, 1)),
        )

        self.identity3 = nn.Sequential(
            nn.Conv2d(self.outChannels[2], self.outChannels[3], (1, 1),# groups=8,
                      bias=False, stride=(1, 1))
        )
        self.cell3 = nn.Sequential(
            nn.Conv2d(self.outChannels[2], self.outChannels[3], (1, 3),# groups=8,
                      padding=(0, 1), bias=False, stride=(1, 1)),
            nn.BatchNorm2d(self.outChannels[3]),
            nn.ReLU(),
            nn.Conv2d(self.outChannels[3], self.outChannels[3], (3, 3),# groups=16,
                      padding=(1, 1), bias=False, stride=(1, 1)),
        )

        self.identity4 = nn.Sequential(
            nn.Conv2d(self.outChannels[3], self.outChannels[4], (1, 1),# groups=16,
                      bias=False, stride=(1, 1))
        )
        self.cell4 = nn.Sequential(
            nn.Conv2d(self.outChannels[3], self.outChannels[4], (1, 3),# groups=16,
                      padding=(0, 1), bias=False, stride=(1, 1)),
            nn.BatchNorm2d(self.outChannels[4]),
            nn.ReLU(),
            nn.Conv2d(self.outChannels[4], self.outChannels[4], (3, 3),# groups=32,
                      padding=(1, 1), bias=False, stride=(1, 1)),
        )

        self.identity5 = nn.Sequential(
            nn.Conv2d(self.outChannels[4], self.outChannels[5], (1, 1),# groups=32,
                      bias=False, stride=(1, 1))
        )
        self.cell5 = nn.Sequential(
            nn.Conv2d(self.outChannels[4], self.outChannels[5], (1, 3),# #groups=32,
                      padding=(0, 1), bias=False, stride=(1, 1)),
            nn.BatchNorm2d(self.outChannels[5]),
            nn.ReLU(),
            nn.Conv2d(self.outChannels[5], self.outChannels[5], (3, 3),# groups=64,
                      padding=(1, 1), bias=False, stride=(1, 1)),
        )

        # -----FCL----- #
        self.fc1 = nn.Linear(self.outChannels[5] * coverageDepth, self.classN)
        # self.fc2 = nn.Linear(1000, self.classN)
        # self.fc3 = nn.LogSoftmax()

    def residual_layer(self, input_data, identity, cell):
        ix = identity(input_data)
        x = cell(input_data)
        LR = nn.ReLU()
        return LR(x + ix)

    def fully_connected_layer(self, x):
        x = self.fc1(x)
        # x = self.fc2(x)
        # if self.training is False:
            # x = self.fc3(x)
        return x

    def forward(self, x):
        out = torch.add(x, 0.001)
        out = self.residual_layer(out, self.identity1, self.cell1)
        out = self.residual_layer(out, self.identity2, self.cell2)
        out = self.residual_layer(out, self.identity3, self.cell3)

        sizes = out.size()
        out = out.view(sizes[0], sizes[1], sizes[3], sizes[2])  # Collapse feature dimension
        sizes = out.size()
        out = out.view(sizes[0], sizes[1] * sizes[2], sizes[3])
        out = out.transpose(1, 2).transpose(0, 1).contiguous()  # TxNxH

        x = self.residual_layer(x, self.identity4, self.cell4)
        x = self.residual_layer(x, self.identity5, self.cell5)
        out = self.fully_connected_layer(out)
        out = out.transpose(0, 1)
        return out
