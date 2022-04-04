import torch
from detectron2.config.defaults import _C as default_config
from detectron2.layers import shape_spec

from zoobot.pytorch.estimators.resnet_detectron2_standard import build_resnet_backbone


def get_resnet(
        input_channels,
        use_imagenet_weights=False,
        include_top=False
    ):

    input_shape = shape_spec.ShapeSpec(height=None, width=None, channels=input_channels, stride=None)

    if use_imagenet_weights:
        raise NotImplementedError  # not implemented yet, could load the detectron2 pretrained imagenet weights if we wanted

    if include_top:
        raise NotImplementedError  # detectron2's version has no top

    base_resnet = build_resnet_backbone(default_config, input_shape)  # exactly matching detectron2's version
    # output is dict of default_config.MODEL.OUT_FEATURES e.g. {'res4': (res4 features)}

    return base_resnet


if __name__ == '__main__':

    import numpy as np

    input_shape = shape_spec.ShapeSpec(height=None, width=None, channels=1, stride=None)

    base_resnet = build_resnet_backbone(default_config, input_shape)  # exactly matching detectron2's version
    # print(base_resnet)

    x = torch.from_numpy(np.random.rand(64, 1, 224, 224)).float()
    print(base_resnet(x))
    print(base_resnet(x).shape)
