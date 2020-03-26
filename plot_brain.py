import pickle
from pyvista_examples import plot


if __name__ == '__main__':

    for brain_idx in range(9):
        with open('./5/data_validation1-{}.pkl'.format(brain_idx), 'rb') as file:
            data, labels, pred = pickle.load(file)

        # print(len(data))
        plot(data, labels, pred)
#

