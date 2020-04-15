#!/usr/bin/env bash

## run the training
python3 train.py \
--dataroot datasets/brains_reg_red50 \
--checkpoints_dir checkpoints/red50_12gb_ep20_step \
--export_folder checkpoints/mesh_collapses \
--name brains \
--ninput_edges 48735 \
--epoch_count 1 \
--norm group \
--num_aug 1 \
--verbose_plot \
--print_freq 10 \
--seed 0 \
--dataset_mode regression \
--niter 1 \
--niter_decay 20 \
--batch_size 1 \
--ncf 64 112 128 \
--pool_res 3000 2750 2500 \
--lr 0.0002 \
--lr_policy step \
--lr_decay_iters 2 \
--init_type kaiming \

