# Sky Scraper Labeling

## Project Setup

### Install uv
Follow the instructions at: https://docs.astral.sh/uv/getting-started/installation/

### Set up the environment
Run:

```
uv venv
source .venv/bin/activate
uv sync
```

If you use windows, run `call .venv/Scripts/activate.bat`

## Usage
* Unzip data into the `data/` folder
* Adjust `DATE` variable in `validation_app.py` to match
* Run streamlit:
```
streamlit run validation_app.py
```
* Ensure that feedback saves to the `feedback/` folder!


