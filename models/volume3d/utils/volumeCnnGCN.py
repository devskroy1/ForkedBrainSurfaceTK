from torch.nn import Module, Conv3d, ConvTranspose3d, Linear, ReLU, Sequential, Linear, Flatten, L1Loss, BatchNorm3d, Dropout, BatchNorm1d
import numpy as np
from torch import nn
import SimpleITK as sitk
import torch
from torch.utils.data import Dataset, DataLoader
import dgl
from dgl.nn.pytorch import GraphConv

class BasicGCNRegressor(nn.Module):
    def __init__(self, in_dim, hidden_dim, n_classes):
        super(BasicGCNRegressor, self).__init__()
        self.conv1 = GraphConv(in_dim, hidden_dim, activation=nn.ReLU())
        self.conv2 = GraphConv(hidden_dim, hidden_dim, activation=nn.ReLU())
        self.predict_layer = nn.Linear(hidden_dim, n_classes)

    def forward(self, graph, features):
        # Perform graph convolution and activation function.
        hidden = self.conv1(graph, features)
        hidden = self.conv2(graph, hidden)
        with graph.local_scope():
            graph.ndata['tmp'] = hidden
            # Calculate graph representation by averaging all the node representations.
            hg = dgl.mean_nodes(graph, 'tmp')

        return self.predict_layer(hg)

class VolumeCNN_GCNRegressor(Module):
    """
    The main CNN
    """

    def __init__(self, feats, dropout_p, in_dim, hidden_dim, device):
        super(VolumeCNN_GCNRegressor, self).__init__()

        self.device = device

        #GCN Regressor
        self.graph_conv1 = GraphConv(in_dim, hidden_dim, activation=nn.ReLU())
        self.graph_conv2 = GraphConv(hidden_dim, hidden_dim, activation=nn.ReLU())

        #VolumeCNN
        self.model = Sequential(
            # 50, 60, 60
            Conv3d(1, feats, padding=0, kernel_size=3, stride=1, bias=True),
            BatchNorm3d(feats),
            ReLU(),
            Conv3d(feats, feats, padding=0, kernel_size=3, stride=1, bias=True),
            BatchNorm3d(feats),
            ReLU(),
            Conv3d(feats, 2*feats, padding=0, kernel_size=2, stride=2, bias=True),
            Dropout(p=dropout_p),

            # 23, 28, 28
            Conv3d(2*feats, 2*feats, padding=0, kernel_size=3, stride=1, bias=True),
            BatchNorm3d(2*feats),
            ReLU(),
            Conv3d(2*feats, 2*feats, padding=0, kernel_size=3, stride=1, bias=True),
            BatchNorm3d(2*feats),
            ReLU(),
            Conv3d(2*feats, 2*2*feats, padding=0, kernel_size=2, stride=2, bias=True),

            # 9, 12, 12
            Conv3d(2*2*feats, 2*2*feats, padding=0, kernel_size=3, stride=1, bias=True),
            BatchNorm3d(2*2*feats),
            ReLU(),
            Conv3d(2*2*feats, 2*2*feats, padding=0, kernel_size=3, stride=1, bias=True),
            BatchNorm3d(2*2*feats),
            ReLU(),
            Conv3d(2*2*feats, 2*2*2*feats, padding=0, kernel_size=1, stride=1, bias=True),
            Dropout(p=dropout_p),

            # 5, 8, 8
            Conv3d(2*2*2*feats, 2*2*2*feats, padding=0, kernel_size=3, stride=1, bias=True),
            # 3, 6, 6
            BatchNorm3d(2*2*2*feats),
            ReLU(),
            Conv3d(2*2*2*feats, 2*2*2*feats, padding=0, kernel_size=3, stride=1, bias=True),
            # 1, 4, 4
            BatchNorm3d(2*2*2*feats),
            ReLU(),
            Conv3d(2*2*2*feats, 2*2*2*2*feats, padding=0, kernel_size=(1, 2, 2), stride=1, bias=True),
            Dropout(p=dropout_p),
            #  1, 3, 3
            Flatten(start_dim=1), # Output: 1
            #Linear(2*2*2*2*feats*(1*3*3), 1),
            )

        self.final_lin_layer = Linear(2*2*2*2*feats*(1*3*3) + hidden_dim, 1)


    def forward(self, x, graph, features):

        gcn_first_feat_map = self.graph_conv1(graph, features)
        gcn_final_feat_map = self.graph_conv2(graph, gcn_first_feat_map)

        vol_conv_feat_map = self.model(x)

        batch_size = vol_conv_feat_map.size(0)
        vol_conv_hidden_dims = vol_conv_feat_map.size(1)
        num_nodes = gcn_final_feat_map.size(0)
        expanded_vol_conv_feat_map = torch.empty((num_nodes, vol_conv_hidden_dims), dtype=torch.float, device=self.device)

        mid = num_nodes // batch_size
        for n in range(batch_size):
            expanded_vol_conv_feat_map[n * mid : (n + 1) * mid, :] = vol_conv_feat_map[n, :]

        # print("gcn_final_feat_map shape")
        # print(gcn_final_feat_map.shape)
        # print("vol_conv_feat_map shape")
        # print(vol_conv_feat_map.shape)
        # print("expanded_vol_conv_feat_map shape")
        # print(expanded_vol_conv_feat_map.shape)

        concat_feat_map = torch.cat((gcn_final_feat_map, expanded_vol_conv_feat_map), dim=1)
        print("concat_feat_map shape")
        print(concat_feat_map.shape)
        print("concat_feat_map")
        print(concat_feat_map)
        return self.final_lin_layer(concat_feat_map)
        #return self.model(x)