from __future__ import print_function

from collections import OrderedDict
from datetime import datetime, date
import numpy as np
import pluck as pluck
import tabulate

from keras.models import Sequential, load_model
from keras.layers.core import Dense, Activation, Dropout
from keras.layers.recurrent import LSTM

from sklearn.preprocessing import MinMaxScaler
from sklearn.metrics import mean_absolute_error

from metrics import MASE, mean_absolute_percentage_error, median_percentage_error, rmse, geh, mape
from utils import load_data, train_test_split, BestWeight


EPS = 1e-6
def step_data(FPATH, end_date=None):
    all_data = load_data(FPATH, EPS, end_date=end_date, use_sensors=[5])
    return all_data


def do_model(all_data, steps, run_model=True):
    _steps = steps
    print("steps:", _steps)
    scaler = MinMaxScaler()
    all_data = scaler.fit_transform(all_data)
    if not run_model:
        return None, None, scaler
    features = all_data[:-_steps]
    labels = all_data[_steps:, -1:]
    tts = train_test_split(features, labels, test_size=0.4)
    X_train = tts[0]
    X_test = tts[1]
    Y_train = tts[2].astype(np.float64)
    Y_test = tts[3].astype(np.float64)



    optimiser = 'adam'
    hidden_neurons = 200
    loss_function = 'mse'
    batch_size = 105
    dropout = 0.056
    inner_hidden_neurons = 269
    dropout_inner = 0.22

    X_train = X_train.reshape((X_train.shape[0], 1, X_train.shape[1]))
    X_test = X_test.reshape(X_test.shape[0], 1, X_test.shape[1])
    print("X train shape:\t", X_train.shape)
    print("X test shape:\t", X_test.shape)
    # print("Y train shape:\t", Y_train.shape)
    # print("Y test shape:\t", Y_test.shape)
    # print("Steps:\t", _steps)
    in_neurons = X_train.shape[2]

    out_neurons = 1

    model = Sequential()
    gpu_cpu = 'cpu'
    best_weight = BestWeight()
    model.add(LSTM(output_dim=hidden_neurons, input_dim=in_neurons, return_sequences=True, init='uniform',
                   consume_less=gpu_cpu))
    model.add(Dropout(dropout))

    dense_input = inner_hidden_neurons
    model.add(LSTM(output_dim=dense_input, input_dim=hidden_neurons, return_sequences=False, consume_less=gpu_cpu))
    model.add(Dropout(dropout_inner))
    model.add(Activation('relu'))

    model.add(Dense(output_dim=out_neurons, input_dim=dense_input))
    model.add(Activation('relu'))

    model.compile(loss=loss_function, optimizer=optimiser)

    history = model.fit(
        X_train, Y_train,
        verbose=0,
        batch_size=batch_size,
        nb_epoch=30,
        validation_split=0.3,
        shuffle=False,
        callbacks=[best_weight]
    )

    model.set_weights(best_weight.get_best())
    predicted = model.predict(X_test) + EPS
    rmse_val = rmse(Y_test, predicted)
    metrics = OrderedDict([
        # ('hidden', hidden_neurons),
        ('steps', _steps),
        ('geh', geh(Y_test, predicted)),
        ('rmse', rmse_val),
        ('mape', mean_absolute_percentage_error(Y_test, predicted)),
        # ('smape', smape(predicted, _Y_test)),
        # ('median_pe', median_percentage_error(predicted, Y_test)),
        # ('mase', MASE(_Y_train, _Y_test, predicted)),
        # ('mae', mean_absolute_error(y_true=Y_test, y_pred=predicted)),
        # ('batch_size', batch_size),
        # ('optimiser', optimiser),
        # ('dropout', dropout),
        # ('extra_layer_dropout', dropout_inner),
        # ('extra_layer_neurons', inner_hidden_neurons),
        # ('loss function', loss_function)
        # 'history': history.history
    ])

    return metrics, model, scaler


if __name__ == "__main__":
    import sys, os
    pass
    try:
        file_path = sys.argv[1]
    except IndexError:
        quit("Usage is: evaluate.py <file_path_1> <file_path_2> ...")
    start = datetime.now()
    for file_path in sys.argv[1:]:
        print ("Examining", file_path)
        data = step_data(file_path, datetime(2013,4,23))
        # metrics = []
        # fname = file_path.split('/')[-1]
        # for i in [1]:#, 3, 6, 9, 12]:
        metric_out, model, scaler = do_model(data, 1, run_model=False)
        model = load_model('models/keras_1_step_3002_scaled.h5')
        #     metrics.append(metric_out)
        #     model.save('models/keras_{}_step_{}_sensor5.h5'.format(i, fname))
        # # model has:       1  1.45893  14.3746  34.0476
        # # print("Loading model")
        # # model = load_model('best_sensor_5_with_calendar.h5')
        # #
        # print("Finished in "+str(datetime.now() - start))
        # print(tabulate.tabulate(metrics, headers='keys', tablefmt="latex"))
        #
        # model = load_model('models/keras_1_step_lane_data_3002_3001.csv_sensor5.h5')
        print("Loading impute data")
        predict_data = load_data(file_path, EPS, use_datetime=True, load_from=datetime(2013, 4, 23), use_sensors=[5], end_date=datetime(2013, 6, 15))
        true_x = predict_data[:, 0]
        true_y = predict_data[:, 1].astype(np.float32)
        # replace 2046/2047 values with 50
        true_y[true_y > 2045] = -1
        pred_y = []
        # flow_val = 8
        for idx, dt in enumerate(true_x):
            in_row = [[
                dt.weekday(),
                # is weekend
                int(dt.weekday() in [5, 6]),
                # hour of day
                dt.isocalendar()[1],
                dt.hour,
                dt.minute,
                max(1, true_y[idx])
            ]]
            in_row = scaler.fit_transform(scaler.fit_transform(in_row))
            pred = model.predict(np.array([in_row]))
            # flow_val = pred[0][0]
            pred_y.append(scaler.inverse_transform([0,0,0,0,0,pred[0][0]]))
        true_x = true_x[1:]
        true_y = true_y[1:]
        pred_y = pred_y[:-1]
        pred_y = np.array(pred_y, dtype=np.float32)
        true_y_max = np.copy(true_y)
        true_y_max[true_y_max == 0] = 1
        print("GEH:  ", np.sqrt(2*np.power(pred_y - true_y_max, 2)/(pred_y + true_y_max)).mean(axis=0))
        print("MAPE: ", mape(true_y_max, pred_y))
        print("RMSE: ", np.sqrt(((pred_y - true_y_max) ** 2).mean(axis=0)))

        import matplotlib.pyplot as plt
        plt.plot(true_x, true_y, 'b-', label='Readings')
        plt.plot(true_x, pred_y, 'r-', label='Predictions')
        df = "%A %d %B, %Y"
        plt.title("3002: Traffic Flow from {} to {}".format(true_x[0].strftime(df), true_x[-1].strftime(df)))
        plt.legend()

        plt.ylabel("Vehicles/ 5 min")
        plt.xlabel("Time")
        plt.show()
