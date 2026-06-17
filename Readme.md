A Python + Streamlit application, implementing a Clean Start decision tree flow and utilizing Microsoft Autogen + LM Studio to generate the final personalized PDF. 

### Key Design Choices:
* **State Management:** Extensively uses `st.session_state` and `st.rerun()` to seamlessly move users backward and forward without losing any previously selected data.
* **Dynamic Custom Routing:** If a user selects "🤔❓Other", they are branched to a distinct text-area stage and safely routed around the irrelevant stages (2–4), landing squarely at Stage 5.
* **AutoGen + Local LM Studio Endpoint:** `autogen.UserProxyAgent` and `autogen.AssistantAgent` are correctly set up via `http://localhost:1234/v1` (the default API endpoint for LM Studio) compiling the responses into a clear, single-shot request.
* **Dynamic PDF Wrapping:** Re-encodes the LLM response safely through `fpdf` and generates a downloadable file in the final UI screen.

### 1. `requirements.txt`
```text
streamlit
pyautogen
fpdf