#!/usr/bin/env bash

## run the training
python3 train.py \
--dataroot datasets/brains_reg_red90 \
--checkpoints_dir checkpoints/red90_12gb_cls_TESTING \
--export_folder checkpoints/mesh_collapses \
--name brains \
--ninput_edges 9000 \
--epoch_count 1 \
--norm group \
--num_aug 1 \
--verbose_plot \
--print_freq 10 \
--seed 0 \
--dataset_mode binary_class \
--niter 5 \
--niter_decay 100 \
--batch_size 14 \
--ncf 64 128 256 \
--pool_res 4000 3500 3250 \
