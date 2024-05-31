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

To compile this tool into an exe, run `setup.py`. The resulting .exe will be inside the `dist` directory.
