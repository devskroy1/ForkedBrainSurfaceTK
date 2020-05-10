import os.path as osp
PATH_TO_ROOT = osp.join(osp.dirname(osp.realpath(__file__)), '..', '..')
import sys
sys.path.append(PATH_TO_ROOT)

import os
import time
import pickle
import csv
import datetime as datetime

import torch
from torch.optim.lr_scheduler import StepLR
import torch_geometric.transforms as T
from torch.utils.tensorboard import SummaryWriter
from torch_geometric.data import DataLoader

from models.pointnet.src.models.pointnet2_classification import Net
from models.pointnet.src.data_loader import OurDataset
from models.pointnet.main.pointnet2_classification import train, test_classification

PATH_TO_ROOT = osp.join(osp.dirname(osp.realpath(__file__)), '..', '..') + '/'
PATH_TO_POINTNET = osp.join(osp.dirname(osp.realpath(__file__)), '..', '..', 'models', 'pointnet') + '/'



if __name__ == '__main__':

    PATH_TO_ROOT = osp.join(osp.dirname(osp.realpath(__file__)), '..') + '/'

    # Model Parameters
    lr = 0.001
    batch_size = 8
    num_workers = 4
    # ['drawem', 'corr_thickness', 'myelin_map', 'curvature', 'sulc'] + ['weight']
    local_features = ['corr_thickness', 'curvature', 'sulc']
    # local_features = []
    global_features = []
    target_class = 'birth_age'
    task = 'classification'
    number_of_points = 500  # 3251# 12000  # 16247

    reprocess = False

    ############# DATA INFORMATION ################
    data = "reducedto_05k"
    data_ending = "05k.vtk"
    type_data_surf = "pial"
    type_data_part = "merged"

    # folder in data/stored for pre-processed data.
    stored = target_class + '/' + type_data_surf + '/' + data + '/' + str(
        local_features + global_features) + '/' + type_data_part
    path = osp.join(osp.dirname(osp.realpath(__file__)), '..', 'data/' + stored)
    data_folder = '/vol/biomedic/users/aa16914/shared/data/dhcp_neonatal_brain/surface_native_04152020/' + \
                  type_data_part + '/' + data + '/' + type_data_surf + '/vtk'

    # sub-CC00466AN13_ses-138400_right_pial_reduce90.vtk
    files_ending = '_' + type_data_part + '_' + type_data_surf + '_' + data_ending
    ###############################################

    ########## INDICES FOR DATA SPLIT #############
    with open(PATH_TO_POINTNET + 'src/names.pk', 'rb') as f:
        indices = pickle.load(f)
    ###############################################


    comment = 'Gender' + str(datetime.datetime.now()) \
              + "__LR__" + str(lr) \
              + "__BATCH_" + str(batch_size) \
              + "__local_features__" + str(local_features) \
              + "__glogal_features__" + str(global_features) \
              + "__number_of_points__" + str(number_of_points) \
              + "__" + data + "__" + type_data_surf + '__no_rotate'

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
        config_file.write('Data res - ' + data + '\n')
        config_file.write('Data type - ' + type_data_surf + '\n')
        config_file.write('Additional comments - With no rotate transforms' + '\n')

    with open(results_folder + '/results.csv', 'w', newline='') as results_file:
        result_writer = csv.writer(results_file, delimiter=',', quotechar='|', quoting=csv.QUOTE_MINIMAL)
        result_writer.writerow(['Patient ID', 'Session ID', 'Prediction', 'Label'])

    # Tensorboard writer.
    writer = SummaryWriter(log_dir='runs/' + task + '/' + comment, comment=comment)

    # DEFINE TRANSFORMS HERE.
    transform = T.Compose([
        T.FixedPoints(number_of_points),
        T.RandomRotate(360, axis=0),
        T.RandomRotate(360, axis=1),
        T.RandomRotate(360, axis=2)
    ])

    # TRANSFORMS DONE BEFORE SAVING THE DATA IF THE DATA IS NOT YET PROCESSED.
    pre_transform = T.NormalizeScale()

    # Creating datasets and dataloaders for train/test/val.
    train_dataset = OurDataset(path, train=True, transform=transform, pre_transform=pre_transform, val=False,
                               target_class=target_class, task=task, reprocess=reprocess, files_ending=files_ending,
                               local_features=local_features, global_feature=global_features,
                               indices=indices['Train'], data_folder=data_folder)

    test_dataset = OurDataset(path, train=False, transform=transform, pre_transform=pre_transform, val=False,
                              target_class=target_class, task=task, reprocess=reprocess, files_ending=files_ending,
                              local_features=local_features, global_feature=global_features,
                              indices=indices['Test'], data_folder=data_folder)

    val_dataset = OurDataset(path, train=False, transform=transform, pre_transform=pre_transform, val=True,
                             target_class=target_class, task=task, reprocess=reprocess, files_ending=files_ending,
                             local_features=local_features, global_feature=global_features,
                             indices=indices['Val'], data_folder=data_folder)

    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True, num_workers=num_workers)
    test_loader = DataLoader(test_dataset, batch_size=1, shuffle=False, num_workers=num_workers)
    val_loader = DataLoader(val_dataset, batch_size=1, shuffle=False, num_workers=num_workers)

    # Getting the number of features to adapt the architecture
    if len(local_features) > 0:
        numb_local_features = train_dataset[0].x.size(1)
    else:
        numb_local_features = 0
    numb_global_features = len(global_features)

    if not torch.cuda.is_available():
        print('YOU ARE RUNNING ON A CPU!!!!')

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    model = Net(numb_local_features, numb_global_features).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    scheduler = StepLR(optimizer, step_size=1, gamma=0.985)

    best_val_acc = 0.0

    # MAIN TRAINING LOOP
    for epoch in range(1, 201):
        start = time.time()
        train(model, train_loader, epoch, device, optimizer, writer)
        val_acc = test_classification(model, val_loader, indices['Val'], device, results_folder, epoch=epoch)

        scheduler.step()

        writer.add_scalar('Acc/val', val_acc, epoch)

        print('Epoch: {:03d}, Validation acc: {:.4f}'.format(epoch, val_acc))
        end = time.time()
        print('Time: ' + str(end - start))
        if val_acc > best_val_acc:
            best_val_acc = val_acc
            torch.save(model.state_dict(), model_dir + '/model_best.pt')
            print('Saving Model'.center(60, '-'))
        writer.add_scalar('Time/epoch', end - start, epoch)

    test_classification(model, test_loader, indices['Test'], device, results_folder, val=False)

    # save the last model
    torch.save(model.state_dict(), model_dir + '/model_last.pt')

    # Eval best model on test
    model.load_state_dict(torch.load(model_dir + '/model_best.pt'))

    with open(results_folder + '/results.csv', 'a', newline='') as results_file:
        result_writer = csv.writer(results_file, delimiter=',', quoting=csv.QUOTE_MINIMAL)
        result_writer.writerow(['Best model!'])

    test_classification(model, test_loader, indices['Test'], device, results_folder, val=False)
