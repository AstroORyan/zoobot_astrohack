import logging
import os
import argparse
import logging
import pandas as pd
# import wandb
import pytorch_lightning as pl
# from pl.strategies.ddp import DDPStrategy
# from pytorch_lightning.strategies import DDPStrategy  # not sure why not importing?
from pytorch_lightning.plugins.training_type import DDPPlugin
from pytorch_lightning.loggers import WandbLogger
from pytorch_lightning.callbacks import ModelCheckpoint
from pytorch_lightning.callbacks.early_stopping import EarlyStopping


from zoobot import schemas, label_metadata
from zoobot.pytorch.estimators import define_model
from zoobot.pytorch.datasets import decals_dr8
from zoobot.pytorch.training import losses

# import wandb

if __name__ == '__main__':

    logging.basicConfig(
      format='%(levelname)s:%(message)s',
      level=logging.INFO
    )


    parser = argparse.ArgumentParser()
    parser.add_argument('--experiment-dir', dest='save_dir', type=str)
    parser.add_argument('--catalog', dest='catalog_loc', type=str)  # expects catalog, not tfrecords
    parser.add_argument('--epochs', dest='epochs', type=int)
    parser.add_argument('--shard-img-size', dest='shard_img_size', type=int, default=300)
    parser.add_argument('--resize-size', dest='resize_size', type=int, default=224)
    parser.add_argument('--batch-size', dest='batch_size', default=256, type=int)
    parser.add_argument('--distributed', default=False, action='store_true')
    parser.add_argument('--color', default=False, action='store_true')
    parser.add_argument('--wandb', default=False, action='store_true')
    parser.add_argument('--test-time-augs', dest='always_augment', default=False, action='store_true',
        help='Zoobot includes keras.preprocessing augmentation layers. \
        These only augment (rotate/flip/etc) at train time by default. \
        They can be enabled at test time as well, which gives better uncertainties (by increasing variance between forward passes) \
        but may be unexpected and mess with e.g. GradCAM techniques.'),
    parser.add_argument('--dropout-rate', dest='dropout_rate', default=0.2, type=float)
    args = parser.parse_args()

    "shared setup"

    # a bit awkward, but I think it is better to have to specify you def. want color than that you def want greyscale
    greyscale = not args.color
    if greyscale:
      logging.info('Converting images to greyscale before training')
      channels = 1
    else:
      logging.warning('Training on color images, not converting to greyscale')
      channels = 3

    catalog_loc = args.catalog_loc
    initial_size = args.shard_img_size
    resize_size = args.resize_size
    batch_size = args.batch_size
    always_augment = not args.always_augment

    epochs = args.epochs
    save_dir = args.save_dir

    assert save_dir is not None
    if not os.path.isdir(save_dir):
      os.mkdir(save_dir)

    pl.seed_everything(42)

    question_answer_pairs = label_metadata.decals_all_campaigns_ortho_pairs
    dependencies = label_metadata.get_decals_ortho_dependencies(question_answer_pairs)
    schema = schemas.Schema(question_answer_pairs, dependencies)
    logging.info('Schema: {}'.format(schema))

    "shared setup ends"

    loss_func = losses.calculate_multiquestion_loss

    model = define_model.ZoobotModel(schema=schema, loss=loss_func)

    catalog = pd.read_csv(catalog_loc)  # debugging .sample(1000)
    catalog['file_loc'] = catalog['file_loc'].str.replace('/raid/scratch',  '/share/nas2')
    logging.info(catalog['file_loc'].iloc[0])

    datamodule = decals_dr8.DECALSDR8DataModule(catalog, schema, greyscale=greyscale)

    if args.wandb:
        # this_script_dir = os.path.dirname(__file__)
        # For weights&biases you need to make this file yourself, with your api key and nothing else
        # with open(os.path.join(this_script_dir, 'wandb_api.txt'), 'r') as f:
        #   api_key = f.readline()
        # wandb.login(key=api_key)
        # wandb.tensorboard.patch(root_logdir=save_dir)
        # wandb.init(sync_tensorboard=True)
        # run wandb login first
        pl_logger = WandbLogger(project='zoobot-pytorch', name='early-stopping')

        pl_logger.experiment.config['label_cols']=schema.label_cols,
        pl_logger.experiment.config['initial_size']=initial_size
        pl_logger.experiment.config['greyscale'] = greyscale
        pl_logger.experiment.config['resize_size'] = resize_size
        pl_logger.experiment.config['batch_size'] = batch_size
        # pl_logger.experiment.config.train_records = train_records
        pl_logger.experiment.config['epochs'] = epochs
        pl_logger.experiment.config['always_augment'] = always_augment
        pl_logger.experiment.config['dropout_rate'] = args.dropout_rate
    else:
        pl_logger = None
    
    callbacks = [
      ModelCheckpoint(
        dirpath=os.path.join(save_dir, 'checkpoints'),
        monitor="val_loss"
        # save_weights_only=True
      ),
      EarlyStopping(monitor='val_loss', patience=8, check_finite=True)
    ]


    trainer = pl.Trainer(
      accelerator="gpu", gpus=2,
      # strategy='ddp',
      strategy=[DDPPlugin(find_unused_parameters=False)],
      logger = pl_logger,
      callbacks=callbacks,
      max_epochs=epochs, default_root_dir=save_dir)
    trainer.fit(model, datamodule)
