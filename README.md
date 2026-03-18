# Ping App

## Installing

Download this repository with:

```bash
git clone https://github.com/JaedanC/Ping-App.git --recursive
```

Install pygui. Download the latest release from [https://github.com/JaedanC/pygui/releases](JaedanC/pygui) and extract:

- 📁 `pygui`
- 📃 `pygui_demo.py`

Then run

```bash
python -m venv venv
./venv/scripts/activate
pip install -r requirements.txt
```

## Running

```bash
./venv/scripts/activate
python app.py
```

## Creating an exe

Note: This does not work for Python 12 and above.

To compile this tool into an exe, additionally install py2exe:

```bash
python -m venv venv-exe
./venv-exe/scripts/activate
pip install -r requirements-exe.txt

pyinstaller app.spec --noconfirm
```

Then run `setup.py`. The resulting .exe will be inside the `dist` directory.
