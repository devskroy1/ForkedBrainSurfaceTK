import torch
import torch.nn.functional as F
from torch.nn import Sequential as Seq, Linear as Lin, ReLU, BatchNorm1d as BN, Flatten, BatchNorm3d, Dropout, Module, Conv3d

from torch_geometric.nn import PointConv, fps, radius, global_max_pool

class SAModule(torch.nn.Module):
    def __init__(self, ratio, r, nn):
        super(SAModule, self).__init__()
        self.ratio = ratio
        self.r = r
        self.conv = PointConv(nn)

    def forward(self, x, pos, batch):
        idx = fps(pos, batch, ratio=self.ratio)
        row, col = radius(pos, pos[idx], self.r, batch, batch[idx],
                          max_num_neighbors=64)  # TODO: FIGURE OUT THIS WITH RESPECT TO NUMBER OF POINTS
        edge_index = torch.stack([col, row], dim=0)
        x = self.conv(x, (pos, pos[idx]), edge_index)
        pos, batch = pos[idx], batch[idx]
        return x, pos, batch


class GlobalSAModule(torch.nn.Module):
    def __init__(self, nn):
        super(GlobalSAModule, self).__init__()
        self.nn = nn

    def forward(self, x, pos, batch):
        x = self.nn(torch.cat([x, pos], dim=1))
        x = global_max_pool(x, batch)
        pos = pos.new_zeros((x.size(0), 3))
        batch = torch.arange(x.size(0), device=batch.device)
        return x, pos, batch


def MLP(channels, batch_norm=True):
    return Seq(*[
        Seq(Lin(channels[i - 1], channels[i]), ReLU(), BN(channels[i]))
        for i in range(1, len(channels))
    ])


# class Net(torch.nn.Module):
#     def __init__(self, num_local_features, num_global_features):
#         super(Net, self).__init__()
#
#         self.num_global_features = num_global_features
#
#         # 3+6 IS 3 FOR COORDINATES, 6 FOR FEATURES PER POINT.
#         # self.sa1_module = SAModule(0.5, 0.2, MLP([3 + num_local_features, 64, 64, 96]))
#         # self.sa1a_module = SAModule(0.5, 0.2, MLP([96 + 3, 96, 96, 128]))
#         # self.sa2_module = SAModule(0.25, 0.4, MLP([128 + 3, 128, 128, 256]))
#         # self.sa3_module = GlobalSAModule(MLP([256 + 3, 256, 512, 1024]))
#
#         self.sa1_module = SAModule(0.5, 0.2, MLP([3 + num_local_features, 64, 64, 128]))
#         #self.sa2_module = SAModule(0.25, 0.4, MLP([128 + 3, 128, 128, 256]))
#         self.sa3_module = GlobalSAModule(MLP([128 + 3, 256, 256, 512]))
#         # self.sa3_module = GlobalSAModule(MLP([256 + 3, 256, 512, 1024]))
#
#         #self.lin1 = Lin(1024 + num_global_features, 512)
#         self.lin1 = Lin(512 + num_global_features, 256)
#         # self.lin2 = Lin(512, 256)
#         # self.lin3 = Lin(256, 128)
#         #self.lin4 = Lin(128, 2)  # OUTPUT = NUMBER OF CLASSES, 1 IF REGRESSION TASK
#         self.lin4 = Lin(256, 2)  # OUTPUT = NUMBER OF CLASSES, 1 IF REGRESSION TASK
#
#     def forward(self, data):
#         # print("Inside pointnet2 clsn forward")
#         # print("Data.x shape")
#         # print(data.x.shape)
#         # print("data.pos shape")
#         # print(data.pos.shape)
#         # print("data.batch shape")
#         # print(data.batch.shape)
#         sa0_out = (data.x, data.pos, data.batch)
#         sa1_out = self.sa1_module(*sa0_out)
#         sa1_x, sa1_pos, sa1_batch = sa1_out
#         # print("sa1_x.shape")
#         # print(sa1_x.shape)
#         # print("sa1_pos.shape")
#         # print(sa1_pos.shape)
#         # print("sa1_batch.shape")
#         # print(sa1_batch.shape)
#
#         #sa1a_out = self.sa1a_module(*sa1_out)
#         #sa1a_x, sa1a_pos, sa1a_batch = sa1a_out
#
#         # print("sa1a_x.shape")
#         # print(sa1a_x.shape)
#         # print("sa1a_pos.shape")
#         # print(sa1a_pos.shape)
#         # print("sa1a_batch.shape")
#         # print(sa1a_batch.shape)
#
#         #sa2_out = self.sa2_module(*sa1a_out)
#         # sa2_out = self.sa2_module(*sa1_out)
#         # x, pos, batch = sa2_out
#         #
#         # print("sa2_x.shape")
#         # print(x.shape)
#         # print("sa2_pos.shape")
#         # print(sa2_pos.shape)
#         # print("sa2_batch.shape")
#         # print(sa2_batch.shape)
#
#        # sa3_out = self.sa3_module(*sa2_out)
#         sa3_out = self.sa3_module(*sa1_out)
#         x, pos, batch = sa3_out
#
#         # print("sa3 x shape")
#         # print(x.shape)
#         # print("sa3 pos shape")
#         # print(pos.shape)
#         # print("sa3 batch shape")
#         # print(batch.shape)
#         # Concatenates global features to the inputs.
#         if self.num_global_features > 0:
#             x = torch.cat((x, data.y[:, 1:self.num_global_features + 1].view(-1, self.num_global_features)), 1)
#
#         x = F.relu(self.lin1(x))
#         # x = F.dropout(x, p=0.5, training=self.training)
#         # x = F.relu(self.lin2(x))
#         # x = F.relu(self.lin3(x))
#         # x = F.dropout(x, p=0.5, training=self.training)
#         x = self.lin4(x)
#         # print("x shape after final lin layer")
#         # print(x.shape)
#         return F.log_softmax(x, dim=-1)

class Net(torch.nn.Module):
    def __init__(self, num_local_features, num_global_features, feats, device, dropout_p=0.5):
        super(Net, self).__init__()

        self.device = device
        self.num_global_features = num_global_features

        #Pointnet++ classification
        # 3+6 IS 3 FOR COORDINATES, 6 FOR FEATURES PER POINT.
        self.sa1_module = SAModule(0.5, 0.2, MLP([3 + num_local_features, 64, 64, 96]))
        self.sa1a_module = SAModule(0.5, 0.2, MLP([96 + 3, 96, 96, 128]))
        self.sa2_module = SAModule(0.25, 0.4, MLP([128 + 3, 128, 128, 256]))
        self.sa3_module = GlobalSAModule(MLP([256 + 3, 256, 512, 1024]))
        self.predict_linear = Lin(2*2*2*2*feats*(1*3*3) + 1024 + num_global_features, 2)

        self.lin1 = Lin(1024 + num_global_features, 512)
        self.lin2 = Lin(512, 256)
        self.lin3 = Lin(256, 128)
        self.lin4 = Lin(128, 2)  # OUTPUT = NUMBER OF CLASSES, 1 IF REGRESSION TASK

        #Volume CNN
        self.volcnn_model = Seq(
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
            Flatten(start_dim=1), # Output: 2
            #Linear(2*2*2*2*feats*(1*3*3), 2),
            )

    def forward(self, vol_cnn_data, data):
        sa0_out = (data.x, data.pos, data.batch)
        sa1_out = self.sa1_module(*sa0_out)
        sa1a_out = self.sa1a_module(*sa1_out)
        sa2_out = self.sa2_module(*sa1a_out)
        sa3_out = self.sa3_module(*sa2_out)
        x, pos, batch = sa3_out

        # print("sa3_out x shape")
        # print(x.shape)
        # Concatenates global features to the inputs.
        if self.num_global_features > 0:
            x = torch.cat((x, data.y[:, 1:self.num_global_features + 1].view(-1, self.num_global_features)), 1)

        # concat_x_pos = torch.cat((data.x, data.pos), dim=1)
        # print("concat_x_pos shape")
        # print(concat_x_pos.shape)

        vol_conv_feat_map = self.volcnn_model(vol_cnn_data)

        # print("vol_conv_feat_map shape")
        # print(vol_conv_feat_map.shape)

        # batch_size = vol_conv_feat_map.size(0)
        # vol_conv_hidden_dims = vol_conv_feat_map.size(1)
        # num_points = x.size(0)
        # expanded_vol_conv_feat_map = torch.empty((num_points, vol_conv_hidden_dims), dtype=torch.float,
        #                                          device=self.device)
        #
        # # print("expanded_vol_conv_feat_map")
        # # print(expanded_vol_conv_feat_map)
        #
        # mid = num_points // batch_size
        # for n in range(batch_size):
        #     # print("vol_conv_feat_map[n, :]")
        #     # print(vol_conv_feat_map[n, :])
        #     expanded_vol_conv_feat_map[n * mid: (n + 1) * mid, :] = vol_conv_feat_map[n, :]
        #
        # print("expanded_vol_conv_feat_map shape")
        # print(expanded_vol_conv_feat_map.shape)

        concat_feat_map = torch.cat((x, vol_conv_feat_map), dim=1)

        x = self.predict_linear(concat_feat_map)

        # x = F.relu(self.lin1(x))
        # # x = F.dropout(x, p=0.5, training=self.training)
        # x = F.relu(self.lin2(x))
        # x = F.relu(self.lin3(x))
        # # x = F.dropout(x, p=0.5, training=self.training)
        # x = self.lin4(x)
        return F.log_softmax(x, dim=-1)