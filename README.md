# PlantUML LLM Diagram tool

[![Open in Streamlit](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://diagrams.streamlit.app/)

## Overview

This app serves as an AI assistant for creating and modifying PlantUML diagrams. Users can interact with the assistant
through a chat interface and directly edit the PlantUML code in a user-friendly way. The app is currently using GPT 4 Omni
Mini.

## Features

- **Interactive Chat**: Engage with an AI assistant to create or modify PlantUML diagrams.
- **Live Editing**: Edit the diagram code directly and see real-time updates.
- **Version History**: View and revert to previous versions of the diagram code easily.

## How to run it on your own machine

1. Export an OpenAI API key `OPENAI_API_KEY`
2. Install the requirements
    ```bash
    $ pip install -r requirements.txt
    ```
3. Run the app
    ```bash
    $ streamlit run streamlit_app.py
    ```
4. Open your browser to access the app interface.
