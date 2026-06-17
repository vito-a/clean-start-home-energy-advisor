import re
import streamlit as st
import autogen
from markdown_pdf import MarkdownPdf, Section
import tempfile
import os

# Set page configuration
st.set_page_config(page_title="Home Energy Advisor", page_icon="🏡", layout="centered")

# Define the Decision Tree Routes
ROUTES = {
    "☀️ Solar Panels": {
        "stage2": {
            "question": "What is your main goal?",
            "options": [
                "💰 Lower my electricity bills",
                "🌱 Reduce my environmental impact",
                "🔋 Add backup power and energy independence",
                "🤔 I'm just exploring my options"
            ]
        },
        "stage3": {
            "question": "Which best describes your home?",
            "options": [
                "I own a single-family home",
                "I own a townhouse or duplex",
                "I live in a condo or HOA community",
                "I'm not sure what options are available for my home"
            ]
        },
        "stage4": {
            "question": "What would you like help with next?",
            "options": [
                "Understanding costs and savings",
                "Checking if my roof is suitable",
                "Learning about incentives and tax credits",
                "Seeing the steps to install solar"
            ]
        }
    },
    "🌡️ Heat Pumps": {
        "stage2": {
            "question": "What are you hoping to improve?",
            "options": [
                "Lower heating and cooling costs",
                "Replace an aging HVAC system",
                "Make my home more comfortable",
                "Reduce fossil fuel use"
            ]
        },
        "stage3": {
            "question": "Which best describes your current heating system?",
            "options": [
                "Natural gas furnace",
                "Electric heating",
                "Oil or propane heating",
                "I'm not sure"
            ]
        },
        "stage4": {
            "question": "What would you like help with next?",
            "options": [
                "Is a heat pump right for my climate?",
                "Estimated installation costs",
                "Available rebates and incentives",
                "Understanding different heat pump types"
            ]
        }
    },
    "🏡 Home Efficiency Upgrades": {
        "stage2": {
            "question": "Which area concerns you most?",
            "options": [
                "High utility bills",
                "Rooms that are too hot or too cold",
                "Drafts and poor insulation",
                "I don't know where my home wastes energy"
            ]
        },
        "stage3": {
            "question": "Which upgrade interests you most?",
            "options": [
                "Better insulation",
                "Air sealing and weatherization",
                "New windows and doors",
                "Home energy assessment"
            ]
        },
        "stage4": {
            "question": "What would you like to learn next?",
            "options": [
                "Which upgrades provide the biggest savings",
                "Typical costs and payback",
                "Rebates and financial assistance",
                "A recommended order for improvements"
            ]
        }
    },
    "🚗 Electric Vehicle & Home Charging": {
        "stage2": {
            "question": "What best describes your situation?",
            "options": [
                "I'm thinking about buying my first EV",
                "I already own an EV",
                "I need home charging",
                "I'm comparing EV ownership with gasoline vehicles"
            ]
        },
        "stage3": {
            "question": "Where would you usually charge?",
            "options": [
                "At home",
                "At work",
                "Public charging stations",
                "I'm not sure yet"
            ]
        },
        "stage4": {
            "question": "What information would help you most?",
            "options": [
                "Installing a home charger",
                "Charging costs and electricity use",
                "Incentives for EVs and chargers",
                "Whether my home's electrical system is ready"
            ]
        }
    }
}

# Final Stage (Stage 5)
STAGE_5_QUESTION = "What would you like to receive?"
STAGE_5_OPTIONS = [
    "📋 A personalized action plan",
    "💵 Estimated costs and incentives",
    "📈 Potential energy and bill savings",
    "🧑‍🔧 Recommended next steps and trusted resources"
]

# Initialize Session State
if 'stage' not in st.session_state:
    st.session_state.stage = 1
if 'answers' not in st.session_state:
    st.session_state.answers = {}
if 'llm_response' not in st.session_state:
    st.session_state.llm_response = None
if 'pdf_path' not in st.session_state:
    st.session_state.pdf_path = None

def next_stage():
    st.session_state.stage += 1

def prev_stage():
    st.session_state.stage -= 1

def jump_to_stage(stage):
    st.session_state.stage = stage

# ---------------------------------------------------------------------------
# Markdown table cleaner / renderer
# ---------------------------------------------------------------------------
def prepare_markdown_for_pdf(text: str) -> str:
    """
    Remove malformed markdown table fragments and render valid tables as DIVs.

    LLMs sometimes emit empty pipe rows such as "| | | |" or orphan table
    separator rows between sections.  PyMuPDF/markdown-pdf can render those as
    visible blue table headers, even when they contain no text.

    Even with clean markdown, PyMuPDF can repeat table backgrounds at page
    breaks. To avoid that renderer bug entirely, valid markdown tables are
    converted to DIV-based faux tables. No <table>, <tr>, <td>, <thead>, or
    <th> elements are emitted on the PDF path.
    """
    def is_pipe_row(line: str) -> bool:
        stripped = line.strip()
        return stripped.startswith('|') and stripped.endswith('|') and len(stripped) > 2

    def split_cells(line: str) -> list[str]:
        stripped = line.strip()
        return [c.strip() for c in stripped[1:-1].split('|')]

    def is_empty_row(cells: list[str]) -> bool:
        empty_values = {'', '&nbsp;', '&#160;'}
        return all(c.lower() in empty_values for c in cells)

    def is_separator_row(cells: list[str]) -> bool:
        return bool(cells) and all(re.fullmatch(r':?-{3,}:?', c) for c in cells)

    def escape_cell(value: str) -> str:
        value = re.sub(r'<br\s*/?>', ' · ', value, flags=re.IGNORECASE)
        value = value.replace('&', '&amp;')
        value = value.replace('<', '&lt;')
        value = value.replace('>', '&gt;')
        value = re.sub(r'`([^`]+)`', r'<code>\1</code>', value)
        value = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', value)
        value = re.sub(r'\*([^*]+)\*', r'<em>\1</em>', value)
        return value

    def render_div_table(header: list[str], body_rows: list[list[str]]) -> list[str]:
        column_count = len(header)
        html = [f'<div class="pdf-div-table pdf-div-cols-{column_count}">']
        html.append(
            '<div class="pdf-div-row pdf-div-header">'
            + ''.join(
                f'<div class="pdf-div-cell">{escape_cell(cell)}</div>'
                for cell in header
            )
            + '</div>'
        )
        for row in body_rows:
            padded_row = row[:column_count] + [''] * max(0, column_count - len(row))
            html.append(
                '<div class="pdf-div-row">'
                + ''.join(
                    f'<div class="pdf-div-cell">{escape_cell(cell)}</div>'
                    for cell in padded_row
                )
                + '</div>'
            )
        html.append('</div>')
        return html

    def clean_table_block(block: list[str]) -> list[str]:
        rows = []
        for raw_line in block:
            line = re.sub(r'<br\s*/?>', ' · ', raw_line, flags=re.IGNORECASE)
            cells = split_cells(line)
            if is_empty_row(cells):
                continue
            rows.append((line, cells, is_separator_row(cells)))

        cleaned: list[str] = []
        separator_seen = False
        for line, _cells, is_separator in rows:
            if is_separator:
                # Keep only the first valid markdown table delimiter:
                # a divider immediately following a non-empty header row.
                if cleaned and not separator_seen and is_pipe_row(cleaned[-1]):
                    cleaned.append(line)
                    separator_seen = True
                continue
            cleaned.append(line)

        if len(cleaned) >= 2:
            header = split_cells(cleaned[0])
            separator = split_cells(cleaned[1])
            if is_separator_row(separator):
                body_rows = [split_cells(row) for row in cleaned[2:]]
                return render_div_table(header, body_rows)

        return cleaned

    lines = text.splitlines()
    result: list[str] = []
    i = 0
    while i < len(lines):
        if is_pipe_row(lines[i]):
            block: list[str] = []
            while i < len(lines) and is_pipe_row(lines[i]):
                block.append(lines[i])
                i += 1
            result.extend(clean_table_block(block))
            continue

        result.append(lines[i])
        i += 1
    return '\n'.join(result)


def protect_signature(text: str) -> str:
    """
    Wrap the closing signature block in an HTML div with page-break-inside:avoid
    so that "Prepared by" and "Date" are never split across two pages.

    The signature is expected to look like:
        Prepared by: Home Energy Advisor ...
        Date: ...
    """
    sig_re = re.compile(
        r'(Prepared by:.*?\n(?:Date:.*?)?)\s*$',
        re.DOTALL | re.IGNORECASE,
    )
    m = sig_re.search(text)
    if m:
        sig = m.group(1).strip()
        replacement = (
            '\n\n<div style="page-break-inside:avoid; margin-top:24pt;">\n\n'
            + sig
            + '\n\n</div>\n'
        )
        text = text[:m.start()] + replacement
    return text


# ---------------------------------------------------------------------------
# Noto Sans font helpers
# Noto Sans is Google's universal Unicode font – it covers virtually all
# Unicode code points including the emoji-adjacent symbols the LLM generates.
# ---------------------------------------------------------------------------
_FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".fonts")
_NOTO_URLS = {
    "NotoSans-Regular.ttf": (
        "https://raw.githubusercontent.com/googlefonts/noto-fonts/main"
        "/hinted/ttf/NotoSans/NotoSans-Regular.ttf"
    ),
    "NotoSans-Bold.ttf": (
        "https://raw.githubusercontent.com/googlefonts/noto-fonts/main"
        "/hinted/ttf/NotoSans/NotoSans-Bold.ttf"
    ),
}


def get_noto_fonts() -> dict[str, str]:
    """Download Noto Sans fonts (once) and return a {variant: absolute_path} dict."""
    import urllib.request

    os.makedirs(_FONT_DIR, exist_ok=True)
    paths: dict[str, str] = {}
    for filename, url in _NOTO_URLS.items():
        dest = os.path.join(_FONT_DIR, filename)
        if not os.path.exists(dest):
            try:
                urllib.request.urlretrieve(url, dest)
            except Exception:
                dest = ""  # fall back to system fonts silently
        if dest and os.path.exists(dest):
            paths[filename] = dest
    return paths


def generate_pdf(text):
    font_paths = get_noto_fonts()
    # Build @font-face rules if we successfully downloaded the fonts
    font_face_css = ""
    body_font = "'Helvetica', 'Arial', sans-serif"
    if font_paths:
        regular = font_paths.get("NotoSans-Regular.ttf", "")
        bold    = font_paths.get("NotoSans-Bold.ttf", "")
        if regular:
            font_face_css += (
                f"@font-face {{"
                f"  font-family: 'NotoSans';"
                f"  font-weight: normal;"
                f"  src: url('{regular}');"
                f"}}\n"
            )
        if bold:
            font_face_css += (
                f"@font-face {{"
                f"  font-family: 'NotoSans';"
                f"  font-weight: bold;"
                f"  src: url('{bold}');"
                f"}}\n"
            )
        if regular:
            body_font = "'NotoSans', 'Arial Unicode MS', sans-serif"
    text = prepare_markdown_for_pdf(text)
    text = protect_signature(text)
    css = font_face_css + """
    @page {
        size: letter;
        margin: 20mm 15mm;
    }
    body {
        font-family: """ + body_font + """;
        color: #334155;
        line-height: 1.5;
        font-size: 11pt;
    }
    h1, h2, h3, h4, h5, h6 {
        color: #1e3a8a;
        font-family: """ + body_font + """;
        margin-top: 20px;
        margin-bottom: 10px;
        font-weight: bold;
    }
    h1 {
        font-size: 20pt;
        border-bottom: 2px solid #2563eb;
        padding-bottom: 8px;
    }
    h2 {
        font-size: 16pt;
        border-bottom: 1px solid #cbd5e1;
        padding-bottom: 6px;
    }
    h3 {
        font-size: 13pt;
    }
    p {
        margin-top: 0;
        margin-bottom: 15px;
    }
    .pdf-div-table {
        display: table;
        table-layout: fixed;
        width: 100%;
        margin-top: 15px;
        margin-bottom: 25px;
        font-size: 9.5pt;
        page-break-inside: avoid;
        break-inside: avoid;
        border: 1px solid #cbd5e1;
    }
    .pdf-div-row {
        display: table-row;
        width: 100%;
    }
    .pdf-div-cell {
        box-sizing: border-box;
        display: table-cell;
        padding: 9px 12px;
        border-bottom: 1px solid #e2e8f0;
        border-right: 1px solid #e2e8f0;
        vertical-align: top;
        font-size: 9.5pt;
        line-height: 1.35;
    }
    .pdf-div-row:last-child .pdf-div-cell {
        border-bottom: 0;
    }
    .pdf-div-row .pdf-div-cell:last-child {
        border-right: 0;
    }
    .pdf-div-header {
        background-color: #f1f5f9;
        color: #1e3a8a;
        font-weight: bold;
        border-bottom: 2px solid #cbd5e1;
    }
    .pdf-div-header .pdf-div-cell {
        padding: 10px 12px;
        border-right-color: #cbd5e1;
    }
    .pdf-div-cols-2 .pdf-div-cell {
        width: 50%;
    }
    .pdf-div-cols-3 .pdf-div-cell {
        width: 33.333333%;
    }
    .pdf-div-cols-4 .pdf-div-cell {
        width: 25%;
    }
    .pdf-div-cols-5 .pdf-div-cell {
        width: 20%;
    }
    table, thead, tbody, tr, th, td {
        background-color: transparent;
        color: inherit;
        border-color: #cbd5e1;
    }
    ul, ol {
        margin-top: 0;
        margin-bottom: 15px;
        padding-left: 20px;
    }
    li {
        margin-bottom: 6px;
    }
    a {
        color: #2563eb;
        text-decoration: none;
    }
    hr {
        border: 0;
        border-top: 1px solid #e2e8f0;
        margin: 25px 0;
    }
    code {
        font-family: 'Courier New', Courier, monospace;
        background-color: #f1f5f9;
        padding: 2px 4px;
        border-radius: 4px;
        font-size: 9.5pt;
    }
    pre {
        background-color: #f1f5f9;
        padding: 15px;
        border-radius: 6px;
        overflow-x: auto;
        margin-bottom: 15px;
    }
    pre code {
        background-color: transparent;
        padding: 0;
        border-radius: 0;
        font-size: 9pt;
    }
    """
    pdf = MarkdownPdf(toc_level=0)
    pdf.add_section(Section(text, toc=False), user_css=css)
    
    # Save to temp file
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    pdf.save(tmp.name)
    return tmp.name

def call_llm_autogen(user_data):
    # Format the user data into a prompt
    prompt = "User has completed a home energy assessment with the following details:\n\n"
    for key, value in user_data.items():
        prompt += f"- {key}: {value}\n"
        
    import datetime
    today = datetime.date.today()
    current_date = f"{today.day} {today.strftime('%B %Y')}"

    prompt += "\n\nPlease generate a personalized, actionable recommendation report based on this information."
    prompt += "\nEnsure the report is structured in clean Markdown. " \
              "Do not wrap the entire report in code blocks or markdown code blocks (e.g. ```markdown). " \
              "Use standard markdown tables without any nested HTML tags (like <br>). " \
              "Do not use empty markdown table rows, blank pipe rows, or table-like rows as spacing between sections. " \
              "Ensure the report ends exactly with the following signature block:\n\n" \
              "Prepared by: Home Energy Advisor – Clean Start Team\n" \
              f"Date: {current_date}\n"

    # Configure LM Studio endpoint (local)
    llm_config = {
        "config_list": [
            {
                "model": "nvidia/nemotron-3-nano-4b", # The model name can be anything for LM Studio
                "base_url": "http://127.0.0.1:1234/v1", # LM Studio default URL
                "api_key": "lm-studio", 
            }
        ],
        "temperature": 0.7,
    }

    # Initialize AutoGen Agents
    assistant = autogen.AssistantAgent(
        name="EnergyAdvisor",
        llm_config=llm_config,
        system_message="You are an expert home energy advisor. Your goal is to provide personalized, " \
        "long and detailed but not too long, highly actionable, and accurate advice. Please format the " \
        "response in clean, standard Markdown. Do not wrap your response in outer markdown code blocks " \
        "like ```markdown or other code wrappers. Use clean markdown tables, headers, and bulleted lists. " \
        "Avoid raw HTML tags. Do not add horizontal lines. Do not use empty pipe rows or table-like " \
        "rows for spacing. Ensure the text is fully readable and " \
        "renders perfectly in a PDF report."
    )

    user_proxy = autogen.UserProxyAgent(
        name="UserProxy",
        human_input_mode="NEVER",
        max_consecutive_auto_reply=0,
        code_execution_config=False
    )

    # Start conversation
    user_proxy.initiate_chat(
        assistant,
        message=prompt
    )

    # Extract last message from assistant
    try:
        messages = user_proxy.chat_messages[assistant]
        if messages:
            return messages[-1]["content"]
    except Exception:
        pass
    return "Error generating response from LLM or empty response received."


# --- UI Layout ---
st.title("🏡 Home Energy Advisor Wizard")

# STAGE 1: Entry Point
if st.session_state.stage == 1:
    st.header("Stage 1: What are you most interested in improving?")
    choice = st.radio("Select an option:", list(ROUTES.keys()) + ["🤔❓Other"], key="stage1_choice")
    
    if st.button("Next"):
        st.session_state.answers["Interest"] = choice
        if choice == "🤔❓Other":
            jump_to_stage(1.5) # Custom routing for 'Other'
        else:
            jump_to_stage(2)
        st.rerun()

# STAGE 1.5: 'Other' Description
elif st.session_state.stage == 1.5:
    st.header("Stage 1: Other (Please Specify)")
    other_desc = st.text_area("Describe what you are interested in improving:")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Back"):
            jump_to_stage(1)
            st.rerun()
    with col2:
        if st.button("Next"):
            if other_desc.strip():
                st.session_state.answers["Interest Details"] = other_desc
                jump_to_stage(5) # Jump straight to final stage
                st.rerun()
            else:
                st.warning("Please provide a description before proceeding.")

# STAGES 2, 3, 4 (Standard Routes)
elif st.session_state.stage in [2, 3, 4]:
    interest = st.session_state.answers.get("Interest")
    stage_key = f"stage{st.session_state.stage}"
    
    # Get data for current stage
    stage_data = ROUTES[interest][stage_key]
    
    st.header(f"Stage {st.session_state.stage}: {stage_data['question']}")
    choice = st.radio("Select an option:", stage_data['options'], key=f"stage_{st.session_state.stage}_choice")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Back"):
            prev_stage()
            st.rerun()
    with col2:
        if st.button("Next"):
            # Save answer
            st.session_state.answers[stage_data['question']] = choice
            next_stage()
            st.rerun()

# STAGE 5: Final Outcome Preferences
elif st.session_state.stage == 5:
    st.header("Stage 5: What would you like to receive?")
    choice = st.radio("Select your preferred outcome:", STAGE_5_OPTIONS, key="stage5_choice")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Back"):
            if st.session_state.answers.get("Interest") == "🤔❓Other":
                jump_to_stage(1.5)
            else:
                jump_to_stage(4)
            st.rerun()
    with col2:
        if st.button("Generate Recommendation"):
            st.session_state.answers["Desired Outcome"] = choice
            st.session_state.llm_response = None
            st.session_state.pdf_path = None
            jump_to_stage(6) # Processing stage
            st.rerun()

# STAGE 6: Processing & PDF Generation
elif st.session_state.stage == 6:
    st.header("Analyzing Your Responses...")
    
    # Display Summary
    st.subheader("Your Selections:")
    for k, v in st.session_state.answers.items():
        st.write(f"**{k}:** {v}")
        
    if st.session_state.llm_response is None:
        st.info("Generating your personalized plan via Autogen & LM Studio. Please wait...")
        
        with st.spinner('Calling LLM...'):
            try:
                # LLM Call
                llm_response = call_llm_autogen(st.session_state.answers)
                st.session_state.llm_response = llm_response
                
                # Create PDF
                pdf_path = generate_pdf(llm_response)
                st.session_state.pdf_path = pdf_path
            except Exception as e:
                st.error(f"An error occurred: {e}")
                
    if st.session_state.llm_response is not None:
        st.subheader("Advisor Report:")
        st.markdown(st.session_state.llm_response)
        
        # Read the generated PDF if it exists
        pdf_path = st.session_state.pdf_path
        if pdf_path and os.path.exists(pdf_path):
            with open(pdf_path, "rb") as f:
                pdf_data = f.read()
                st.download_button(
                    label="📄 Download Recommendation PDF",
                    data=pdf_data,
                    file_name="Energy_Recommendation_Plan.pdf",
                    mime="application/pdf"
                )
        
        st.write("---")
        if st.button("🔄 Start Over"):
            st.session_state.stage = 1
            st.session_state.answers = {}
            st.session_state.llm_response = None
            st.session_state.pdf_path = None
            st.rerun()
