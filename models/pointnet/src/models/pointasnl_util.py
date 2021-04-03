from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import numpy as np
import os
import sys
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch_geometric.nn import PointConv, fps, radius, global_max_pool, knn
from models.pointnet.src.models.pytorch_utils import conv1d, conv2d

#from torch_points_kernels import knn

# BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# ROOT_DIR = os.path.dirname(BASE_DIR)
# sys.path.append(os.path.join(ROOT_DIR, 'utils'))
# sys.path.append(os.path.join(ROOT_DIR, 'tf_ops/sampling'))
# sys.path.append(os.path.join(ROOT_DIR, 'tf_ops/grouping'))
# sys.path.append(os.path.join(ROOT_DIR, 'tf_ops/3d_interpolation'))
# from tf_interpolate import three_nn, three_interpolate
# import tf_grouping
# import tf_sampling
# import tf_util
# import nearest_neighbors.lib.python.nearest_neighbors as nearest_neighbors


def knn_query(k, support_pts, query_pts):
    """
    :param support_pts: points you have, B*N1*3
    :param query_pts: points you want to know the neighbour index, B*N2*3
    :param k: Number of neighbours in knn search
    :return: neighbor_idx: neighboring points indexes, B*N2*k
    """

    neighbor_idx = nearest_neighbors.knn_batch(support_pts, query_pts, k, omp=True)
    return neighbor_idx.astype(np.int32)

# def knn(x, k):
#     print("Inside knn function")
#     print("x shape")
#     print(x.shape)
#     inner = -2 * torch.matmul(x.transpose(1, 0), x)
#     xx = torch.sum(x ** 2, dim=1, keepdim=True)
#     print("inner shape")
#     print(inner.shape)
#     print("xx.shape")
#     print(xx.shape)
#     # pairwise_distance = -xx - inner - xx.transpose(2, 1)
#     pairwise_distance = -xx - inner - xx.transpose(1, 0)
#     idx = pairwise_distance.topk(k=k, dim=-1)[1]  # (batch_size, num_points, k)
#     return idx

def grouping(feature, K, src_xyz, q_xyz, use_xyz=True, use_knn=True, radius=0.2):
    '''
    K: neighbor size
    src_xyz: original point xyz (batch_size, ndataset, 3)
    q_xyz: query point xyz (batch_size, npoint, 3)
    '''

    batch_size = src_xyz.size(0)
    npoint = q_xyz.size(1)

    if use_knn:
        #point_indices = tf.py_func(knn_query, [K, src_xyz, q_xyz], tf.int32)

        #TODO: Use pytorch geometric knn as torch points kernels knn not implemented on CUDA
        #Work out how to get rid of batch dimension
        point_indices = knn(src_xyz, q_xyz, K)

        # batch_indices = tf.tile(tf.reshape(tf.range(batch_size), (-1, 1, 1, 1)), (1, npoint, K, 1))
        # idx = tf.concat([batch_indices, tf.expand_dims(point_indices, axis=3)], axis=3)
        # idx.set_shape([batch_size, npoint, K, 2])
        # grouped_xyz = tf.gather_nd(src_xyz, idx)

        batch_indices = torch.tile(torch.arange(0, batch_size).view(-1, 1, 1, 1), (1, npoint, K, 1))

        idx = torch.cat([batch_indices, point_indices.expand(3)], dim=3)
        idx = idx.reshape([batch_size, npoint, K, 2])

        if feature is None:

            params_size = list(src_xyz.size())

            assert len(idx.size()) == 2
            assert len(params_size) >= idx.size(1)
            # Generate indices
            idx = idx.t().long()
            ndim = idx.size(0)
            index = torch.zeros_like(idx[0]).long()
            m = 1

            for i in range(ndim)[::-1]:
                index += idx[i] * m
                m *= src_xyz.size(i)

            src_xyz = src_xyz.reshape((-1, *tuple(torch.tensor(src_xyz.size()[ndim:]))))
            grouped_xyz = src_xyz[index]

    #TODO: Implement gather_nd in pytorch
    grouped_feature = tf.gather_nd(feature, idx)

    if use_xyz:
        grouped_feature = torch.cat([grouped_xyz, grouped_feature], dim=-1)

    return grouped_xyz, grouped_feature, idx

def weight_net_hidden(xyz, hidden_units, scope, is_training, bn_decay=None, weight_decay = None, activation_fn=nn.ReLU):

    net = xyz
    #mod_list = nn.ModuleList()
    for i, num_hidden_units in enumerate(hidden_units):
        net = conv2d(net, num_hidden_units, kernel_size=[1,1], padding=0, stride=[1,1], bn=True,
                     is_training=is_training, activation_fn=activation_fn, bn_decay=bn_decay, weight_decay=weight_decay)
    return net

def nonlinear_transform(data_in, mlp, scope, is_training, bn_decay=None, weight_decay = None, activation_fn=nn.ReLU):

    #with tf.variable_scope(scope) as sc:

    net = data_in
    l = len(mlp)
    if l > 1:
        for i, out_ch in enumerate(mlp[0:(l-1)]):
            net = conv2d(net, out_ch, kernel_size=[1, 1],
                                padding=0, stride=[1, 1],
                                bn=True, is_training=is_training, activation_fn=nn.ReLU,
                                bn_decay=bn_decay, weight_decay=weight_decay)

            #net = tf_util.dropout(net, keep_prob=0.5, is_training=is_training, scope='dp_nonlinear%d'%(i))
    net = conv2d(net, mlp[-1], kernel_size=[1, 1],
                        padding=0, stride=[1, 1],
                        bn=False, is_training=is_training, bn_decay=bn_decay,
                        activation_fn=nn.Sigmoid, weight_decay=weight_decay)

    return net

def SampleWeights(new_point, grouped_xyz, mlps, is_training, bn_decay, weight_decay, scope, bn=True, scaled=True):
    """Input
        grouped_feature: (batch_size, npoint, nsample, channel) TF tensor
        grouped_xyz: (batch_size, npoint, nsample, 3)
        new_point: (batch_size, npoint, nsample, channel)
        Output
        (batch_size, npoint, nsample, 1)
    """
    [batch_size, npoint, nsample, channel] = list(new_point.size())
    bottleneck_channel = max(32,channel//2)
    # normalized_xyz = grouped_xyz - tf.tile(torch.unsqueeze(grouped_xyz[:, :, 0, :], 2), [1, 1, nsample, 1])
    normalized_xyz = grouped_xyz - torch.tile(torch.unsqueeze(grouped_xyz[:, :, 0, :], 2), (1, 1, nsample, 1))
    new_point = torch.cat([normalized_xyz, new_point], dim=-1) # (batch_size, npoint, nsample, channel+3)

    mod_list = nn.ModuleList()

    # transformed_feature = nn.conv2d(new_point, bottleneck_channel * 2, [1, 1],
    #                                      padding='VALID', stride=[1, 1],
    #                                      bn=bn, is_training=is_training,
    #                                      scope='conv_kv_ds', bn_decay=bn_decay, weight_decay=weight_decay,
    #                                      activation_fn=None)

    transformed_feature = conv2d(new_point, bottleneck_channel * 2, kernel_size=[1, 1],
                                 padding=0, stride=[1,1], bn=bn, is_training=is_training,
                                 bn_decay=bn_decay, weight_decay=weight_decay,
                                 activation_fn=None)

    # transformed_new_point = nn.conv2d(new_point, bottleneck_channel, [1, 1],
    #                                        padding='VALID', stride=[1, 1],
    #                                        bn=bn, is_training=is_training,
    #                                        scope='conv_query_ds', bn_decay=bn_decay, weight_decay=weight_decay,
    #                                        activation_fn=None)

    transformed_new_point = conv2d(new_point, bottleneck_channel, kernel_size=[1, 1],
                                   padding=0, stride=[1,1],
                                   bn=bn, is_training=is_training,
                                   bn_decay=bn_decay, weight_decay=weight_decay,
                                   activation_fn=None)

    transformed_feature1 = transformed_feature[:, :, :, :bottleneck_channel]
    feature = transformed_feature[:, :, :, bottleneck_channel:]

    weights = torch.matmul(transformed_new_point, transformed_feature1)  # (batch_size, npoint, nsample, nsample)
    if scaled:
        bottleneck_channel = bottleneck_channel.type(torch.FloatTensor)
        weights = weights / torch.sqrt(bottleneck_channel)
    softmax = nn.Softmax(dim=-1)
    weights = softmax(weights)
    channel = bottleneck_channel

    new_group_features = torch.matmul(weights, feature)
    new_group_features = torch.reshape(new_group_features, (batch_size, npoint, nsample, channel))
    for i, c in enumerate(mlps):
        activation = nn.ReLU() if i < len(mlps) - 1 else None
        new_group_features = conv2d(new_group_features, c, kernel_size=[1, 1],
                                           padding=0, stride=[1, 1],
                                           bn=bn, is_training=is_training,
                                           bn_decay=bn_decay, weight_decay=weight_decay,
                                           activation_fn=activation)

    softmax = nn.Softmax(dim=2)
    new_group_weights = softmax(new_group_features)
    # new_group_weights = nn.softmax(new_group_features, axis=2)  # (batch_size, npoint,nsample, mlp[-1)
    return new_group_weights

def AdaptiveSampling(group_xyz, group_feature, num_neighbor, is_training, bn_decay, weight_decay, scope, bn):
    # with tf.variable_scope(scope) as sc:
    [nsample, num_channel] = list(group_feature.size()[-2:])
    if num_neighbor == 0:
        new_xyz = group_xyz[:, :, 0, :]
        new_feature = group_feature[:, :, 0, :]
        return new_xyz, new_feature
    shift_group_xyz = group_xyz[:, :, :num_neighbor, :]
    shift_group_points = group_feature[:, :, :num_neighbor, :]
    sample_weight = SampleWeights(shift_group_points, shift_group_xyz, [32, 1 + num_channel], is_training, bn_decay, weight_decay, scope, bn)
    # new_weight_xyz = tf.tile(torch.unsqueeze(sample_weight[:,:,:, 0],-1), [1, 1, 1, 3])
    new_weight_xyz = torch.tile(torch.unsqueeze(sample_weight[:, :, :, 0], -1), (1, 1, 1, 3))
    new_weight_feature = sample_weight[:,:,:, 1:]
    new_xyz = torch.sum(torch.multiply(shift_group_xyz, new_weight_xyz))
    new_feature = torch.sum(torch.multiply(shift_group_points, new_weight_feature))

    return new_xyz, new_feature

def PointNonLocalCell(feature,new_point,mlp,is_training, bn_decay, weight_decay, scope, bn=True, scaled=True, mode='dot'):
    """Input
        feature: (batch_size, ndataset, channel) TF tensor
        new_point: (batch_size, npoint, nsample, channel)
        Output
        (batch_size, npoint, nsample, channel)
    """
    #with tf.variable_scope(scope) as sc:
    bottleneck_channel = mlp[0]
    batch_size, npoint, nsample, channel = new_point.get_shape()
    ndataset = feature.get_shape()[1]
    feature = torch.unsqueeze(feature, dim=2) #(batch_size, ndataset, 1, channel)
    # transformed_feature = tf_util.conv2d(feature, bottleneck_channel * 2, [1,1],
    #                                         padding='VALID', stride=[1,1],
    #                                         bn=bn, is_training=is_training,
    #                                         scope='conv_kv', bn_decay=bn_decay, weight_decay = weight_decay, activation_fn=None)

    transformed_feature = nn.conv2d(feature, bottleneck_channel * 2, kernel_size=(1, 1), padding=0, stride=1)
    bn = nn.BatchNorm2d()

    # transformed_new_point = nn.conv2d(new_point, bottleneck_channel, [1,1],
    #                                         padding='VALID', stride=[1,1],
    #                                         bn=bn, is_training=is_training,
    #                                         scope='conv_query', bn_decay=bn_decay, weight_decay = weight_decay, activation_fn=None) #(batch_size, npoint, nsample, bottleneck_channel)

    transformed_new_point = nn.conv2d(new_point, bottleneck_channel, kernel_size=(1, 1), padding=0, stride=1)
    bn = nn.BatchNorm2d()

    transformed_new_point = torch.reshape(transformed_new_point, [batch_size, npoint*nsample, bottleneck_channel])
    transformed_feature1 = torch.squeeze(transformed_feature[:,:,:,:bottleneck_channel], dim=2) #(batch_size, ndataset, bottleneck_channel)
    transformed_feature2 = torch.squeeze(transformed_feature[:,:,:,bottleneck_channel:], dim=2) #(batch_size, ndataset, bottleneck_channel)
    if mode == 'dot':
        attention_map = torch.matmul(transformed_new_point, transformed_feature1) #(batch_size, npoint*nsample, ndataset)
        if scaled:
            bottleneck_channel = bottleneck_channel.type(torch.FloatTensor)
            attention_map = attention_map / torch.sqrt(bottleneck_channel)

    elif mode == 'concat':
        tile_transformed_feature1 = torch.tile(torch.unsqueeze(transformed_feature1, dim=1),(1,npoint*nsample,1,1)) # (batch_size,npoint*nsample, ndataset, bottleneck_channel)
        tile_transformed_new_point = torch.tile(torch.reshape(transformed_new_point, (batch_size, npoint*nsample, 1, bottleneck_channel)), (1,1,ndataset,1)) # (batch_size,npoint*nsample, ndataset, bottleneck_channel)
        merged_feature = torch.cat([tile_transformed_feature1,tile_transformed_new_point], dim=-1)

        # attention_map = tf_util.conv2d(merged_feature, 1, [1,1],
        #                                     padding='VALID', stride=[1,1],
        #                                     bn=bn, is_training=is_training,
        #                                     scope='conv_attention_map', bn_decay=bn_decay, weight_decay = weight_decay)

        attention_map = nn.conv2d(new_point, bottleneck_channel, kernel_size=(1, 1), padding=0, stride=1)

        attention_map = torch.reshape(attention_map, (batch_size, npoint*nsample, ndataset))
    softmax = nn.Softmax(dim=-1)
    attention_map = softmax(attention_map)
    new_nonlocal_point = torch.matmul(attention_map, transformed_feature2) #(batch_size, npoint*nsample, bottleneck_channel)
    # new_nonlocal_point = tf_util.conv2d(tf.reshape(new_nonlocal_point,[batch_size,npoint, nsample, bottleneck_channel]), mlp[-1], [1,1],
    #                                         padding='VALID', stride=[1,1],
    #                                         bn=bn, is_training=is_training,
    #                                         scope='conv_back_project', bn_decay=bn_decay, weight_decay = weight_decay)

    new_nonlocal_point = nn.conv2d(torch.reshape(new_nonlocal_point,[batch_size,npoint, nsample, bottleneck_channel]), mlp[-1], kernel_size=(1, 1), padding=0, stride=1)

    new_nonlocal_point = torch.squeeze(new_nonlocal_point, dim=1)  # (batch_size, npoints, mlp2[-1])

    return new_nonlocal_point

def PointASNLSetAbstraction(xyz, feature, npoint, nsample, mlp, is_training, bn_decay, weight_decay, scope, bn=True, use_knn=True, radius=None, as_neighbor=8, NL=True):
    ''' Input:
            xyz: (batch_size, ndataset, 3) TF tensor
            feature: (batch_size, ndataset, channel) TF tensor
            point: int32 -- #points sampled in Euclidean space by farthest point sampling
            nsample: int32 -- how many points in each local region
            mlp: list of int32 -- output size for MLP on each point
        Return:
            new_xyz: (batch_size, npoint, 3) TF tensor
            new_points: (batch_size, npoint, mlp[-1] or mlp2[-1]) TF tensor
    '''
    #with tf.variable_scope(scope) as sc:

    batch_size, num_points, num_channel = feature.get_shape()
    '''Farthest Point Sampling'''
    if num_points == npoint:
        new_xyz = xyz
        new_feature = feature
    else:
        new_xyz, new_feature = sampling(npoint, xyz, feature)

    grouped_xyz, new_point, idx = grouping(feature, nsample, xyz, new_xyz,use_knn=use_knn,radius=radius)
    nl_channel = mlp[-1]

    '''Adaptive Sampling'''
    if num_points != npoint:
        new_xyz, new_feature = AdaptiveSampling(grouped_xyz, new_point, as_neighbor, is_training, bn_decay, weight_decay, scope, bn)
    grouped_xyz -= torch.tile(torch.unsqueeze(new_xyz, 2), (1, 1, nsample, 1))  # translation normalization
    new_point = torch.cat([grouped_xyz, new_point], dim=-1)

    '''Point NonLocal Cell'''
    if NL:
        new_nonlocal_point = PointNonLocalCell(feature, tf.expand_dims(new_feature, axis=1),
                                               [max(32, num_channel//2), nl_channel],
                                               is_training, bn_decay, weight_decay, scope, bn)

    '''Skip Connection'''
    skip_spatial = torch.max(new_point, dim=2)

    # skip_spatial = tf_util.conv1d(skip_spatial, mlp[-1], 1,padding='VALID', stride=1,
    #                              bn=bn, is_training=is_training, scope='skip',
    #                              bn_decay=bn_decay, weight_decay=weight_decay)

    skip_spatial = nn.conv1d(skip_spatial,  mlp[-1], kernel_size=(1, 1), padding=0, stride=1)

    '''Point Local Cell'''
    for i, num_out_channel in enumerate(mlp):
        if i != len(mlp) - 1:
            # new_point = tf_util.conv2d(new_point, num_out_channel, [1,1],
            #                             padding='VALID', stride=[1,1],
            #                             bn=bn, is_training=is_training,
            #                             scope='conv%d'%(i), bn_decay=bn_decay, weight_decay = weight_decay)

            new_point = nn.conv2d(new_point, num_out_channel, kernel_size=(1, 1), padding=0, stride=1)

    weight = weight_net_hidden(grouped_xyz, [32], scope = 'weight_net', is_training=is_training, bn_decay = bn_decay, weight_decay = weight_decay)
    new_point = torch.transpose(new_point, [0, 1, 3, 2])
    new_point = torch.matmul(new_point, weight)
    new_point = tf_util.conv2d(new_point, mlp[-1], [1,new_point.get_shape()[2].value],
                                    padding=0, stride=[1,1],
                                    bn=bn, is_training=is_training,
                                    scope='after_conv', bn_decay=bn_decay, weight_decay = weight_decay)

    new_point = tf.squeeze(new_point, [2])  # (batch_size, npoints, mlp2[-1])

    new_point = tf.add(new_point,skip_spatial)

    if NL:
        new_point = tf.add(new_point, new_nonlocal_point)

    '''Feature Fushion'''
    new_point = tf_util.conv1d(new_point, mlp[-1], 1,
                              padding=0, stride=1, bn=bn, is_training=is_training,
                              scope='aggregation', bn_decay=bn_decay, weight_decay=weight_decay)

    return new_xyz, new_point

def placeholder_inputs(batch_size, num_point, channel):
    pointclouds_pl = tf.placeholder(tf.float32, shape=(batch_size, num_point, 3))
    feature_pts_pl = tf.placeholder(tf.float32, shape=(batch_size, num_point, channel))
    labels_pl = tf.placeholder(tf.int32, shape=(batch_size, num_point))
    return pointclouds_pl, feature_pts_pl, labels_pl



def get_repulsion_loss(pred, nsample=20, radius=0.07):
    # pred: (batch_size, npoint,3)
    idx, pts_cnt = tf_grouping.query_ball_point(radius, nsample, pred, pred)
    tf.summary.histogram('smooth/unque_index', pts_cnt)

    grouped_pred = tf_grouping.group_point(pred, idx)  # (batch_size, npoint, nsample, 3)
    grouped_pred -= tf.expand_dims(pred, 2)

    ##get the uniform loss
    h = 0.03
    dist_square = tf.reduce_sum(grouped_pred ** 2, axis=-1)
    dist_square, idx = tf.nn.top_k(-dist_square, 5)
    dist_square = -dist_square[:, :, 1:]  # remove the first one
    dist_square = tf.maximum(1e-12,dist_square)
    dist = tf.sqrt(dist_square)
    weight = tf.exp(-dist_square/h**2)
    uniform_loss = tf.reduce_mean(radius-dist*weight)
    return uniform_loss