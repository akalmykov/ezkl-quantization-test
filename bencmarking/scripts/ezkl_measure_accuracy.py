import argparse
import json
import os
import pickle
import tempfile
import asyncio

import ezkl
import torch
import torchvision
import torchvision.transforms as transforms
# Needed to load pickle file
from ezkl_train_mnist import LeNet


async def predict(x, model, tmpdir, settings_path, model_path):

    input_filename = os.path.join(tmpdir, "input.json")
    output_filename = os.path.join(tmpdir, "output.json")

    torch_out = model(x)
    _, predicted = torch.max(torch_out, 1)

    data_array = ((x).detach().numpy()).reshape([-1]).tolist()
    data = dict(input_shapes=[x.shape[1:]] * x.shape[0],
                input_data=[data_array],
                output_data=[((o).detach().numpy()).reshape([-1]).tolist() for o in torch_out])

    with open(input_filename, "w") as f:
        json.dump(data, f)

    res = await ezkl.gen_witness(input_filename, model_path,
                     output_filename, settings_path)

    with open(output_filename, "r") as f:
        scores = json.load(f)["output_data"]
    _, predicted_quantized = torch.max(torch.tensor(scores), 1)

    return predicted, predicted_quantized


async def compute_accuracy(model, tmpdir, run_args, model_path):

    transform = transforms.Compose([
        transforms.ToTensor(),
        transforms.Normalize((0.1307,), (0.3081,))
    ])
    test_dataset = torchvision.datasets.MNIST(
        root='./data', train=False, transform=transform)
    # Only works with batch size 1?
    test_loader = torch.utils.data.DataLoader(
        dataset=test_dataset, batch_size=1, shuffle=False)

    total = 0
    correct = 0
    correct_quantized = 0

    settings_path = os.path.join(tmpdir, "settings.json")
    ezkl.gen_settings(
        model_path, settings_path, run_args)

    for i, (images, labels) in enumerate(test_loader):
        predicted, predicted_quantized = await predict(
            images, model, tmpdir, settings_path, model_path)

        total += labels.size(0)
        correct += (predicted == labels).sum().item()
        correct_quantized += (predicted_quantized == labels).sum().item()

        if (i + 1) % 1000 == 0:
            print(f"Example {i + 1} of {len(test_dataset)}")

    print(f"Measured accuracy on {total} samples")

    accuracy = 100 * correct / total
    accuracy_quantized = 100 * correct_quantized / total
    print(
        f'Test Accuracy: {accuracy:.2f}% (original), {accuracy_quantized:.2f}% (quantized)')


if __name__ == "__main__":
    loop = asyncio.new_event_loop()  # Here
    asyncio.set_event_loop(loop)  # Here

    parser = argparse.ArgumentParser()
    parser.add_argument('--model', help='Path to the ONNX file', required=True)
    parser.add_argument('--scale', help='EZKL Scale argument', required=True)
    parser.add_argument('--bits', help='EZKL Bits argument', required=True)
    parser.add_argument(
        '--logrows', help='EZKL LogRows argument', required=True)
    args = parser.parse_args()

    print(args.scale)
    model_path = args.model

    run_args = ezkl.PyRunArgs()
    run_args.input_scale = int(args.scale)
    run_args.param_scale = int(args.scale)
    # run_args.bits = int(args.bits)
    run_args.logrows = int(args.logrows)

    # Assume the pickle file is next to the ONNX file
    pickle_path = model_path[:-len(".onnx")] + ".pkl"

    with open(pickle_path, "rb") as f:
        model = pickle.load(f)

    with torch.no_grad():
        with tempfile.TemporaryDirectory() as tempdir:

            loop.run_until_complete(compute_accuracy(model, tempdir, run_args, model_path))
