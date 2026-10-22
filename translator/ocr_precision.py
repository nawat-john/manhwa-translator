"""FP16 network weights/compute with FP32 outputs for EasyOCR postprocessing."""
import torch


class FP16Network(torch.nn.Module):
    def __init__(self, network):
        super().__init__()
        self.network = network.half().eval()

    def forward(self, *args):
        args = tuple(value.half() if isinstance(value, torch.Tensor) and value.is_floating_point()
                     else value for value in args)
        result = self.network(*args)
        if isinstance(result, tuple):
            return tuple(value.float() for value in result)
        return result.float()


def use_fp16(reader):
    if str(reader.device).split(':')[0] != 'cuda':
        raise ValueError('EasyOCR FP16 requires CUDA; use the original reader on CPU')
    reader.detector = FP16Network(reader.detector)
    reader.recognizer = FP16Network(reader.recognizer)
