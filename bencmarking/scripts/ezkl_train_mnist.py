import argparse
import pickle

import torch
import torchvision
import torchvision.transforms as transforms
from torch import nn, optim

# from ezkl import export


class LeNet(nn.Module):
    def __init__(self, features=(6, 16, 120, 84)):
        super(LeNet, self).__init__()

        features = list(features)
        if len(features) == 3:
            features.append(None)

        f1, f2, f3, f4 = features

        self.conv1 = nn.Conv2d(1, f1, kernel_size=5)
        self.conv2 = nn.Conv2d(f1, f2, kernel_size=5)
        self.fc1 = nn.Linear(f2 * 4 * 4, f3)
        if f4 is not None:
            self.fc2 = nn.Linear(f3, f4)
            self.fc3 = nn.Linear(f4, 10)
        else:
            self.fc2 = nn.Linear(f3, 10)
            self.fc3 = None

    def forward(self, x):
        # Note that tanh activation does a better job at keeping activations in a predictable
        # range. This means that fewer bits are needed for quantization!
        x = torch.tanh(self.conv1(x))
        x = torch.nn.functional.avg_pool2d(x, 2)
        x = torch.tanh(self.conv2(x))
        x = torch.nn.functional.avg_pool2d(x, 2)
        x = x.flatten(1)
        x = torch.tanh(self.fc1(x))
        x = self.fc2(x)
        if self.fc3 is not None:
            x = self.fc3(torch.tanh(x))
        return x


def load_dataset(batch_size=64):
    transform = transforms.Compose([
        transforms.ToTensor(),
        transforms.Normalize((0.1307,), (0.3081,))
    ])

    train_dataset = torchvision.datasets.MNIST(
        root='./data', train=True, transform=transform, download=True)
    test_dataset = torchvision.datasets.MNIST(
        root='./data', train=False, transform=transform)

    train_loader = torch.utils.data.DataLoader(
        dataset=train_dataset, batch_size=batch_size, shuffle=True)
    test_loader = torch.utils.data.DataLoader(
        dataset=test_dataset, batch_size=batch_size, shuffle=False)

    return train_loader, test_loader


def train(model, train_dataset, learning_rate=0.001, num_epochs=10):

    # Define the loss function and optimizer
    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(model.parameters(), lr=learning_rate)

    # Train the LeNet model
    total_step = len(train_dataset)
    for epoch in range(num_epochs):
        for i, (images, labels) in enumerate(train_dataset):

            # Forward pass
            outputs = model(images)
            loss = criterion(outputs, labels)

            # Backward and optimize
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

            if (i + 1) % 100 == 0:
                print(
                    f'Epoch [{epoch + 1}/{num_epochs}], Step [{i + 1}/{total_step}], Loss: {loss.item():.4f}')


def evaluate(model, test_dataset):
    model.eval()
    with torch.no_grad():
        total = 0
        correct = 0
        for images, labels in test_dataset:
            outputs = model(images)
            _, predicted = torch.max(outputs.data, 1)
            total += labels.size(0)
            correct += (predicted == labels).sum().item()

        accuracy = 100 * correct / total
        print(f'Test Accuracy: {accuracy:.2f}%')


if __name__ == "__main__":
    from six.moves import urllib
    opener = urllib.request.build_opener()
    opener.addheaders = [('User-agent', 'Mozilla/5.0')]
    urllib.request.install_opener(opener)

    parser = argparse.ArgumentParser()
    parser.add_argument('--features', nargs='+',
                        help='Number of feature maps per layer (either 3 or 4)', required=True)
    args = parser.parse_args()

    features = args.features
    assert len(features) in [
        3, 4], "Number of feature maps per layer must be either 3 or 4"
    features = [int(f) for f in features]

    features_str = "_".join([str(f) for f in features])

    train_dataset, test_dataset = load_dataset()

    model = LeNet(features)

    train(model, train_dataset)
    evaluate(model, test_dataset)

    with open(f"models/lenet_{features_str}.pickle", "wb") as f:
        pickle.dump(model, f)

    # Use first text example
    input_array = next(iter(test_dataset))[0][0].detach().numpy()
    # Input to the model
    # torch_out = circuit(input_array)
    # Export the model
    torch.onnx.export(model,  # model being run
                      # model input (or a tuple for multiple inputs)
                      input_array,
                      # where to save the model (can be a file or file-like object)
                      "models/lenet_{features_str}.onnx",
                      export_params=True,  # store the trained parameter weights inside the model file
                      opset_version=10,  # the ONNX version to export the model to
                      do_constant_folding=True,  # whether to execute constant folding for optimization
                      input_names=['input'],  # the model's input names
                      output_names=['output'],  # the model's output names
                      dynamic_axes={'input': {0: 'batch_size'},  # variable length axes
                                    'output': {0: 'batch_size'}})

    # export(model, input_array=input_array, input_shape=[
    #        1, 28, 28], onnx_filename=f"models/lenet_{features_str}.onnx", input_filename="models/input.json")
