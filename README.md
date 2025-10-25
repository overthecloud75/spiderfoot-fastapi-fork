# SpiderFoot-FastAPI-Fork

Forked from [SpiderFoot](https://github.com/smicallef/spiderfoot) by Steve Micallef, licensed under the MIT License.

This fork modernizes the SpiderFoot web interface by replacing the original CherryPy-based UI with a **FastAPI** backend and **Jinja2** templates for rendering, instead of the original Mako templates. Future updates will include a redesigned UI for credential management and other improvements.

## Changes in this fork

- **Web framework updated**: CherryPy → FastAPI
- **Template engine updated**: Mako → Jinja2
- **Improved modularity**: Separation of web and core scanning logic
- **UI improvements**: Ready for credential and configuration management enhancements

## Installation

Follow the original SpiderFoot installation instructions, with adjustments for FastAPI:

```bash
git clone https://github.com/overthecloud75/spiderfoot-fastapi-fork.git
cd spiderfoot-fastapi-fork
pip install -r requirements.txt
python3 main.py

