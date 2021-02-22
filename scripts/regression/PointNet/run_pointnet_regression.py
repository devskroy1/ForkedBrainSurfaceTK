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
from torch.utils.data import ConcatDataset, Subset, DataLoader
from torch.utils.tensorboard import SummaryWriter

from models.pointnet.src.models.pointnet2_regression_v2 import Net
from models.pointnet.main.pointnet2 import train, test_regression

from models.pointnet.src.utils import get_data_path, data, drop_points

PATH_TO_ROOT = osp.join(osp.dirname(osp.realpath(__file__)), '..', '..', '..') + '/'
PATH_TO_POINTNET = osp.join(osp.dirname(osp.realpath(__file__)), '..', '..', '..', 'models', 'pointnet') + '/'

if __name__ == '__main__':

    num_workers = 2
    local_features = []
    global_features = []

    #################################################
    ########### EXPERIMENT DESCRIPTION ##############
    #################################################
    recording = True
    REPROCESS = False

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

    print("test_dataset[0].x.size(0)")
    print(test_dataset[0].x.size(0))
    print("test_dataset[1].x.size(0)")
    print(test_dataset[1].x.size(0))
    print("len(test_dataset)")
    print(len(test_dataset))

    print("train_dataset[0]")
    print(train_dataset[0])
    print("len(train_dataset[0])")
    print(len(train_dataset[0]))

    if len(local_features) > 0:
        numb_local_features = train_dataset[0].x.size(1)
    else:
        numb_local_features = 0
    numb_global_features = len(global_features)

    # 7. Create the model
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
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
    #TODO: Remove this
    # drop_points(model, test_loader, 0)

    num_test_points = test_dataset[0].x.size(0)
    complete_list_indices = range(num_test_points)
    complete_list_indices_tensor = torch.Tensor(complete_list_indices)
    max_i = int(num_test_points / 1000)

    for i in range(max_i):
        list_datasets = []
        #Feature importance: use segmentn region dropping instead of points dropping
        #Ensure you are dropping for each subject
        #Could use features of segmentn, drop labels of segmentn
        #Could use points under any region in the segmentn.
        #Extract points for which label == 1, label == 39 etc. Get index by label and drop points by label.
        #Might need padding if point size is not the same.
        for d in range(len(test_dataset)):
            print("len(test_dataset[d].x)")
            print(len(test_dataset[d].x))
            valid_indices = torch.cat((complete_list_indices_tensor[0:(i * 1000)],
                                      complete_list_indices_tensor[(i + 1) * 1000:]))
            # print("valid_indices")
            # print(valid_indices)
            # subset_x = Subset(test_dataset[d].x, valid_indices)
            # print("len(subset_x)")
            # print(len(subset_x))
            # subset_pos = Subset(test_dataset[d].pos, valid_indices)

            test_subset = Subset(test_dataset[d], valid_indices)
            print("test_subset")
            print(test_subset)
            print("len(test_subset)")
            print(len(test_subset))
            #test_dataset_combined = ConcatDataset([subset_x, subset_pos, test_dataset[d].y])
            # print("test_dataset_combined.x")
            # print(test_dataset_combined.x)
            # print("test_dataset_combined.pos")
            # print(test_dataset_combined.pos)
            # print("test_dataset_combined.y")
            # print(test_dataset_combined.y)
            list_datasets.append(test_subset)
        test_dataset_combined = ConcatDataset(list_datasets)
        print("test_dataset_combined")
        print(test_dataset_combined)
        test_dataloader_dropped = DataLoader(test_dataset_combined, batch_size=batch_size, shuffle=False,
                                             num_workers=num_workers)
        print("test_dataloader_dropped")
        print(test_dataloader_dropped)
        # for dropped_data, data in zip(test_dataloader_dropped, test_loader):
        for dropped_data in test_dataloader_dropped:
            print("dropped data")
            print(dropped_data)
            pred_dropped = model(dropped_data)
            print("pred_dropped")
            print(pred_dropped)

            # original_pred = model(data)
            # importance = abs(pred_dropped - original_pred)

    for epoch in range(1, numb_epochs + 1):
        start = time.time()
        prediction = train(model, train_loader, epoch, device,
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

        num_test_points = test_dataset[0].x.size(0)
        complete_list_indices = range(num_test_points)
        complete_list_indices_tensor = torch.Tensor(complete_list_indices)
        max_i = num_test_points / 1000

        for i in range(max_i):
            list_datasets = []
            for d in range(len(test_dataset)):
                valid_indices = torch.cat(complete_list_indices_tensor[0:(i * 1000)],
                                          complete_list_indices_tensor[(i + 1) * 1000:])
                subset_x = Subset(test_dataset[d].x, valid_indices)
                subset_pos = Subset(test_dataset[d].pos, valid_indices)
                test_dataset_combined = ConcatDataset([subset_x, subset_pos, test_dataset[d].y])
                list_datasets.append(test_dataset_combined)
            test_dataset_combined = ConcatDataset(list_datasets)
            test_dataloader_dropped = DataLoader(test_dataset_combined, batch_size=batch_size, shuffle=False,
                                                 num_workers=num_workers)
            for dropped_data, data in zip(test_dataloader_dropped, test_loader):
                pred_dropped = model(dropped_data)
                original_pred = model(data)
                importance = abs(pred_dropped - original_pred)

    #Keep this here
    #drop_points(train_loader, model)
    # drop_points(train_loader)
    if recording:
        # save the last model
        torch.save(model.state_dict(), model_dir + '/model_last.pt')

        # Eval best model on test
        model.load_state_dict(torch.load(model_dir + '/model_best.pt'))

        with open(results_folder + '/results.csv', 'a', newline='') as results_file:
            result_writer = csv.writer(results_file, delimiter=',', quoting=csv.QUOTE_MINIMAL)
            result_writer.writerow(['Best model!'])

        test_regression(model, test_loader, indices['Test'], device, recording, results_folder, val=False)
