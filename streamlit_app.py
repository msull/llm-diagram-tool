import time

import streamlit as st
from logzero import logger
from plantuml import PlantUML
from pydantic import BaseModel

from supersullytools.llm.agent import AgentTool, ChatAgent
from supersullytools.llm.trackers import SessionUsageTracking
from supersullytools.streamlit.chat_agent_utils import ChatAgentUtils
from supersullytools.streamlit.misc import simple_fixed_container
from supersullytools.utils.common_init import get_standard_completion_handler
from supersullytools.utils.misc import date_id

st.set_page_config(layout="wide", initial_sidebar_state="collapsed")


def main():
    if "session_id" not in st.session_state:
        st.session_state.session_id = date_id()

    if "diagram_code_versions" not in st.session_state:
        st.session_state.diagram_code_versions = []

    if "toggle_key_counter" not in st.session_state:
        st.session_state.toggle_key_counter = 0

    if "diagram_code" not in st.session_state:
        st.session_state.diagram_code = """
@startuml
actor User
participant "Chat Panel" as Chat
participant "Code Panel" as Code
participant "Render Panel" as Render

User -> Chat : Type message
Chat -> User : Assistant replies
User -> Code : Edit diagram code
Code -> Render : Automatically update diagram
@enduml
    """.strip()

    agent = get_agent(st.session_state.session_id)
    agent_utils = ChatAgentUtils(agent, use_system_slash_cmds=False)


    col1, col2, col3 = st.columns(3)

    display_code = st.session_state.diagram_code

    with col2:
        with simple_fixed_container():
            placeholder = st.empty()
            if st.toggle(
                "View Previous Versions",
                key=f"view_previous{st.session_state.toggle_key_counter}",
            ):
                if not st.session_state.diagram_code_versions:
                    st.write("No previous versions available")
                else:
                    minus_version = st.number_input(
                        "Versions back",
                        min_value=0,
                        max_value=len(st.session_state.diagram_code_versions),
                    )
                    if minus_version == 0:
                        st.caption("This is the current version")
                    else:
                        go_back = minus_version * -1
                        s = "s" if minus_version > 1 else ""
                        st.caption(f"This is {minus_version} edit{s} ago")
                        display_code = st.session_state.diagram_code_versions[go_back]
                        if st.button("Replace current with this version"):
                            st.session_state.diagram_code_versions.append(
                                st.session_state.diagram_code
                            )
                            st.session_state.diagram_code = display_code
                            st.session_state.toggle_key_counter += 1
                            st.rerun()
                    st.code(display_code)

            else:
                edited = placeholder.text_area(
                    "Diagram Code:",
                    st.session_state.diagram_code,
                    height=600,
                    label_visibility="collapsed",
                )
                if edited != st.session_state.diagram_code:
                    st.session_state.diagram_code_versions.append(
                        st.session_state.diagram_code
                    )
                    st.session_state.diagram_code = edited
                    st.rerun()

    with col3:
        with simple_fixed_container():
            if display_code:
                st.image(get_uml_diagram_svg(display_code))

    with col1:
        agent.add_to_context("current_diagram", st.session_state.diagram_code)

        before = st.session_state.diagram_code
        agent_utils.display_chat_and_run_agent(include_function_calls=False)
        after = st.session_state.diagram_code
        if before != after:
            st.session_state.diagram_code_versions.append(before)
            st.rerun()

        if agent.get_chat_history():
            st.caption(
                "It's generally useful to wipe the chat history any time "
                'you are done with a particular "feature" or independent change on the diagram.'
            )
            st.button(
                "Clear chat history",
                help="Wipe out the chat history without erasing the diagram code",
                on_click=agent.reset_history,
            )

        chat_msg = st.chat_input(max_chars=600)

        if chat_msg:
            if agent_utils.add_user_message(chat_msg):
                time.sleep(0.01)
                st.rerun()

        st.caption(
            "👋 Welcome to your AI UML Assistant! You can chat to create or modify UML diagrams, "
            "or edit the code directly in the panel. You can also ask to explain the current code. "
            "Need inspiration? Check out [Real World PlantUML](https://real-world-plantuml.com/) "
            "for examples and starting points. "
            "How would you like to begin?"
        )


AGENT_DESCRIPTION = """
You are an AI assistant engaging in a conversation about UML diagrams of any type. Your role is to help the user in understanding, creating, and modifying UML diagrams as requested. 

You also have the ability to directly update the diagram code whenever the user requests changes. You have continuous access to the current state of the UML diagram code, allowing you to keep track of the latest version and apply modifications accurately.

Make sure to present explanations in a way that the user can not only understand the content of the diagram but also appreciate the underlying structure and precise context of the UML. Make each modification traceable by explaining your updates step-by-step.

# Instructions for Interaction
- Ask follow-up questions when necessary to clarify the user's needs regarding modifications or areas of concern.
- Always explain the modifications you are making before updating the code. Break down how the changes will affect the final diagram.
- Use easy-to-understand language, while highlighting key components of UML diagrams such as Classes, Relationships, Dependencies, etc.
- Be ready to handle different types of UML diagrams such as Class, Sequence, Activity, Use Case, etc.

# Usage of the Diagram Modification Tool
When the user asks for changes to be made to the active UML diagram, you may directly modify the current state of the diagram code.

- Before you execute a change, explain what you are about to alter. This makes sure the user understands what will happen to the diagram.
- Be as explicit as possible when describing updates. Include the specific diagram elements, such as relationships, classes, or entities, affected by the changes.

# Steps
1. **Understand User Intent**: Ensure you completely grasp what type of UML diagram the user is referring to and the modifications they need.
2. **Provide Reasoning for Updates**: Describe in detail how the requested changes affect the diagram. Highlight any relevant relationships or structures affected.
3. **Make Code Changes**: Use the given tool to modify the diagram code. Update the state of the UML accordingly.
4. **Confirm the Changes**: Let the user view the updated raw code and rendered UML diagram, and ask if the latest changes meet their expectations.

# Notes
- Remember that different types of UML diagrams (e.g., sequence vs. class diagrams) have different components and purposes. Adjust your explanations accordingly.
- Avoid making changes without confirming with the user, particularly when there's ambiguity in their request.
- Whenever changes are made, make sure the explanation precedes the code to maintain transparency.
- Do not directly put the code into the chat with the user (other than snippets for explanations when needed)
""".strip()


class UpdateUmlDiagramCode(BaseModel):
    diagram_code: str


def handle_update_uml_diagram_tool(params: UpdateUmlDiagramCode):
    st.session_state.diagram = get_uml_diagram_svg(params.diagram_code)
    st.session_state.diagram_code = params.diagram_code
    get_agent(st.session_state.session_id).add_to_context(
        "current_diagram", st.session_state.diagram_code
    )
    return "Diagram updated!"


@st.cache_resource
def get_agent(session_id: str) -> ChatAgent:
    _ = session_id
    tool_profiles = {
        "all": [
            AgentTool(
                name=UpdateUmlDiagramCode.__name__,
                params_model=UpdateUmlDiagramCode,
                mechanism=handle_update_uml_diagram_tool,
                safe_tool=True,
            )
        ]
    }
    return ChatAgent(
        agent_description="You are a helpful assistant.",
        logger=logger,
        completion_handler=get_standard_completion_handler(
            include_session_tracker=False,
            extra_trackers=[get_session_usage_tracker(st.session_state.session_id)],
            store_source_tag="diagram-tool",
            topics=["diagram-tool"],
            enable_bedrock=False,
        ),
        tool_profiles=tool_profiles,
        max_consecutive_tool_calls=1,
        default_completion_model="GPT 4 Omni Mini",
        require_reason=False,
    )


@st.cache_resource
def get_session_usage_tracker(session_id: str) -> SessionUsageTracking:
    _ = session_id
    return SessionUsageTracking()


@st.cache_data
def get_uml_diagram_svg(uml_code):
    url = PlantUML(url="http://www.plantuml.com/plantuml/img/")
    return url.get_url(uml_code)


if __name__ == "__main__":
    main()
