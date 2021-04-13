import os.path as osp

PATH_TO_ROOT = osp.join(osp.dirname(osp.realpath(__file__)), '..', '..', '..')
import sys

sys.path.append(PATH_TO_ROOT)

import os
import time
import pickle
import csv

import torch
from torch.optim.lr_scheduler import StepLR
from torch.utils.tensorboard import SummaryWriter

from models.pointnet.src.models.pointnet2_regression_v2 import Net
from models.pointnet.main.pointnet2 import train, test_regression

from models.pointnet.src.utils import get_data_path, data
from models.pointnet.src.models.pointnet_randla_net import RandLANet

PATH_TO_ROOT = osp.join(osp.dirname(osp.realpath(__file__)), '..', '..', '..') + '/'
PATH_TO_POINTNET = osp.join(osp.dirname(osp.realpath(__file__)), '..', '..', '..', 'models', 'pointnet') + '/'

if __name__ == '__main__':

    num_workers = 2
    local_features = ['corrected_thickness', 'curvature', 'sulcal_depth']
    global_features = []

    #################################################
    ########### EXPERIMENT DESCRIPTION ##############
    #################################################
    recording = True
    REPROCESS = True

    data_nativeness = 'native'
    data_compression = "10k"
    data_type = 'white'
    hemisphere = 'both'

    # data_nativeness = 'native'
    # data_compression = "10k"
    # data_type = 'pial'
    # hemisphere = 'both'

    comment = 'comment'

    #################################################
    ############ EXPERIMENT DESCRIPTION #############
    #################################################

    # 1. Model Parameters
    ################################################
    lr = 0.001
    batch_size = 2
    gamma = 0.9875
    scheduler_step_size = 2
    target_class = 'scan_age'
    task = 'regression'
    numb_epochs = 200
    number_of_points = 10000

    ################################################

    ########## INDICES FOR DATA SPLIT #############
    with open(PATH_TO_POINTNET + 'src/names.pk', 'rb') as f:
        indices = pickle.load(f)
    ###############################################

    data_folder, files_ending = get_data_path(data_nativeness, data_compression, data_type, hemisphere=hemisphere)

    train_dataset, test_dataset, validation_dataset, train_loader, test_loader, val_loader, num_labels = data(
        data_folder,
        files_ending,
        data_type,
        target_class,
        task,
        REPROCESS,
        local_features,
        global_features,
        indices,
        batch_size,
        num_workers=2,
        data_nativeness=data_nativeness,
        data_compression=data_compression,
        hemisphere=hemisphere
    )

    if len(local_features) > 0:
        numb_local_features = train_dataset[0].x.size(1)
    else:
        numb_local_features = 0
    numb_global_features = len(global_features)

    d_in = numb_local_features
    print("d_in")
    print(d_in)
    print("Num labels - should be 1")
    print(num_labels)

    # 7. Create the model
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print("torch.cuda.is_available()")
    print(torch.cuda.is_available())

    #model = RandLANet(d_in=d_in, num_classes=1, device=device)
    model = Net(numb_local_features, numb_global_features).to(device)

    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    scheduler = StepLR(optimizer, step_size=scheduler_step_size, gamma=gamma)

    print(f'number of param: {sum(p.numel() for p in model.parameters() if p.requires_grad)}')

    #################################################
    ############# EXPERIMENT LOGGING ################
    #################################################
    writer = None
    results_folder = None
    if recording:

        # Tensorboard writer.
        writer = SummaryWriter(log_dir='runs/' + task + '/' + comment, comment=comment)

        results_folder = 'runs/' + task + '/' + comment + '/results'
        model_dir = 'runs/' + task + '/' + comment + '/models'

        if not osp.exists(results_folder):
            os.makedirs(results_folder)

        if not osp.exists(model_dir):
            os.makedirs(model_dir)

        with open(results_folder + '/configuration.txt', 'w', newline='') as config_file:
            config_file.write('Learning rate - ' + str(lr) + '\n')
            config_file.write('Batch size - ' + str(batch_size) + '\n')
            config_file.write('Local features - ' + str(local_features) + '\n')
            config_file.write('Global feature - ' + str(global_features) + '\n')
            config_file.write('Number of points - ' + str(number_of_points) + '\n')
            config_file.write('Data res - ' + data_compression + '\n')
            config_file.write('Data type - ' + data_type + '\n')
            config_file.write('Data nativeness - ' + data_nativeness + '\n')
            # config_file.write('Additional comments - With rotate transforms' + '\n')

        with open(results_folder + '/results.csv', 'w', newline='') as results_file:
            result_writer = csv.writer(results_file, delimiter=',', quotechar='|', quoting=csv.QUOTE_MINIMAL)
            result_writer.writerow(['Patient ID', 'Session ID', 'Prediction', 'Label', 'Error'])

    #################################################
    #################################################

    best_val_loss = 999

    # MAIN TRAINING LOOP
    for epoch in range(1, numb_epochs + 1):
        start = time.time()
        train(model, train_loader, epoch, device,
              optimizer, scheduler, writer)

        val_mse, val_l1 = test_regression(model, val_loader,
                                          indices['Val'], device,
                                          recording, results_folder,
                                          epoch=epoch)

        if recording:
            writer.add_scalar('Loss/val_mse', val_mse, epoch)
            writer.add_scalar('Loss/val_l1', val_l1, epoch)

            print('Epoch: {:03d}, Test loss l1: {:.4f}'.format(epoch, val_l1))
            end = time.time()
            print('Time: ' + str(end - start))
            if val_l1 < best_val_loss:
                best_val_loss = val_l1
                torch.save(model.state_dict(), model_dir + '/model_best.pt')
                print('Saving Model'.center(60, '-'))
            writer.add_scalar('Time/epoch', end - start, epoch)

        test_regression(model, test_loader, indices['Test'], device, recording, results_folder, val=False)

    if recording:
        # save the last model
        torch.save(model.state_dict(), model_dir + '/model_last.pt')

        # Eval best model on test
        model.load_state_dict(torch.load(model_dir + '/model_best.pt'))

        with open(results_folder + '/results.csv', 'a', newline='') as results_file:
            result_writer = csv.writer(results_file, delimiter=',', quoting=csv.QUOTE_MINIMAL)
            result_writer.writerow(['Best model!'])

        test_regression(model, test_loader, indices['Test'], device, recording, results_folder, val=False)
