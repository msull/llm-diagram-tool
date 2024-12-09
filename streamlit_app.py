import random
import time

import streamlit as st
from logzero import logger
from plantuml import PlantUML
from pydantic import BaseModel
from supersullytools.llm.agent import AgentTool, ChatAgent
from supersullytools.llm.trackers import SessionUsageTracking
from supersullytools.streamlit.chat_agent_utils import ChatAgentUtils
from supersullytools.utils.common_init import get_standard_completion_handler
from supersullytools.utils.misc import date_id

st.set_page_config(
    page_title="PlantUML Diagram Editor",
    layout="wide",
    initial_sidebar_state="collapsed",
)


def main():
    if "session_id" not in st.session_state:
        st.session_state.session_id = date_id()

    if "diagram_code_versions" not in st.session_state:
        st.session_state.diagram_code_versions = []

    if "toggle_key_counter" not in st.session_state:
        st.session_state.toggle_key_counter = 0

    if "diagram_code" not in st.session_state:
        st.session_state.diagram_code = DEFAULT_DIAGRAM_CODE

    agent = get_agent(st.session_state.session_id)
    agent_utils = ChatAgentUtils(agent, use_system_slash_cmds=False)

    col1, col2, col3 = st.columns(3)
    # col1, col3 = st.columns(2)

    display_code = st.session_state.diagram_code

    with col2:
        with st.container():
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
                    st.code(display_code)

            else:
                edited = placeholder.text_area(
                    "diagram code",
                    st.session_state.diagram_code,
                    height=600,
                    # label_visibility="collapsed",
                )
                if edited != st.session_state.diagram_code:
                    st.session_state.diagram_code_versions.append(
                        st.session_state.diagram_code
                    )
                    st.session_state.diagram_code = edited
                    st.rerun()

    with col3:
        this_theme = st.selectbox(
            "theme", THEMES, None, disabled="!theme" in display_code
        )
        if "!theme" not in display_code and not this_theme:
            if "random_theme" not in st.session_state:
                st.session_state.random_theme = random.choice(THEMES)

            this_theme = st.session_state.random_theme
            if this_theme:
                with st.container(border=True):
                    st.caption(f'Shown with theme "{this_theme}"')

                    def _remove():
                        st.session_state.random_theme = None

                    st.button("Remove", on_click=_remove, use_container_width=True)

        if display_code:
            if this_theme:
                lines = display_code.splitlines()
                lines.insert(1, f"!theme {this_theme}")
                display_code = "\n".join(lines)
            st.image(get_uml_diagram_svg(display_code))

    with col1:
        chat_msg = st.chat_input(placeholder="message to ai", max_chars=1000)
        # chat_msg = st.text_area('message to ai', max_chars=600, height=300)
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
        agent.add_to_context("current_diagram", st.session_state.diagram_code)

        before = st.session_state.diagram_code
        display_chat_and_run_agent(agent_utils, include_function_calls=False)
        after = st.session_state.diagram_code
        if before != after:
            st.session_state.diagram_code_versions.append(before)
            st.rerun()

        if chat_msg:
            if agent_utils.add_user_message(chat_msg):
                time.sleep(0.01)
                st.rerun()

        if not agent.get_chat_history():
            st.caption(
                "👋 Welcome to your AI PlantUML Assistant! You can chat to create or modify PlantUML diagrams, "
                "or edit the code directly in the panel. You can also ask to explain the current code. "
                "Need inspiration? Check out [Real World PlantUML](https://real-world-plantuml.com/) "
                "for examples and starting points. PlantUML can produce an incredible variety of diagram types. "
                "The [PlantUML Theme Gallery](https://the-lum.github.io/puml-themes-gallery/diagrams/index.html) "
                "is another great resource."
            )

    if (
        not agent.get_chat_history()
        and st.session_state.diagram_code == DEFAULT_DIAGRAM_CODE
    ):
        st.subheader("Example Diagrams")
        cols = iter(st.columns(3))
        for idx, title in enumerate(DIAGRAM_EXAMPLES):
            if idx % 3 == 0:
                cols = iter(st.columns(3))

            code = DIAGRAM_EXAMPLES[title]
            with next(cols).container(border=True):
                st.write(f"**{title}**")
                st.popover("code", use_container_width=True).code(code)
                st.image(get_uml_diagram_svg(code))
                if st.button(
                    "Load this diagram",
                    key=f"load-{title}",
                    use_container_width=True,
                    type="primary",
                ):
                    st.session_state.diagram_code = code
                    st.rerun()


def display_chat_and_run_agent(agent_utils, include_function_calls=True):
    num_chat_before = len(
        agent_utils.chat_agent.get_chat_history(
            include_function_calls=include_function_calls
        )
    )

    new_messages = st.container()

    previous_msg_role = ""
    for msg in reversed(
        agent_utils.chat_agent.get_chat_history(
            include_function_calls=include_function_calls
        )
    ):
        if msg.role == previous_msg_role:
            st.divider()
        previous_msg_role = msg.role
        with st.chat_message(msg.role):
            agent_utils.display_chat_msg(msg.content)

    with new_messages:
        if agent_utils.chat_agent.working:
            with st.status("Agent working...", expanded=True) as status:
                # Define the callback function within the scope of `status`
                def status_callback_fn(message):
                    status.update(label=f"Agent working... {message}", state="running")
                    st.write(message)

                # Run the agent loop, passing the callback function
                while agent_utils.chat_agent.working:
                    agent_utils.chat_agent.run_agent(
                        status_callback_fn=status_callback_fn
                    )
                    time.sleep(0.05)

                # Final status update when the agent completes
                status.update(
                    label="Agent completed work!", state="complete", expanded=False
                )

        # output any new messages
        for msg in agent_utils.chat_agent.get_chat_history(
            include_function_calls=include_function_calls
        )[num_chat_before:]:
            with st.chat_message(msg.role):
                agent_utils.display_chat_msg(msg.content)


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
- The user can see the diagram and current version of the code at all times so do not repeat the code to them, other than small snippets if needed for explanations
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
        agent_description=AGENT_DESCRIPTION,
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


@st.cache_resource()
def get_uml_diagram_svg(uml_code):
    logger.info("Getting diagram from remote")
    url = PlantUML(url="http://www.plantuml.com/plantuml/img/")
    return url.get_url(uml_code)


THEMES = [
    "amiga",
    "aws-orange",
    "black-knight",
    "bluegray",
    "blueprint",
    "carbon-gray",
    "cerulean-outline",
    "cerulean",
    "cloudscape-design",
    "crt-amber",
    "crt-green",
    "cyborg-outline",
    "cyborg",
    "hacker",
    "lightgray",
    "mars",
    "materia-outline",
    "materia",
    "metal",
    "mimeograph",
    "minty",
    "mono",
    "_none_",
    "plain",
    "reddress-darkblue",
    "reddress-darkgreen",
    "reddress-darkorange",
    "reddress-darkred",
    "reddress-lightblue",
    "reddress-lightgreen",
    "reddress-lightorange",
    "reddress-lightred",
    "sandstone",
    "silver",
    "sketchy-outline",
    "sketchy",
    "spacelab-white",
    "spacelab",
    "sunlust",
    "superhero-outline",
    "superhero",
    "toy",
    "united",
    "vibrant",
]

DEFAULT_DIAGRAM_CODE = """
@startuml
actor User
participant "Chat Panel" as Chat
participant "Code Panel" as Code
participant "Render Panel" as Render

User -> Chat : Type message
Chat -> User : AI replies
Chat -> Code: AI Edits diagram code
User -> Code : Manually Edit diagram code
Code -> Render : Automatically update diagram
@enduml
""".strip()

DIAGRAM_EXAMPLES = {
    "JSON Diagram": """
@startjson
{
  "title": "Pizza Ordering Workflow",
  "actors": ["Customer", "PizzaApp", "PizzaChef", "DeliveryDriver"],
  "steps": [
    { "from": "Customer", "to": "PizzaApp", "action": "Order Pineapple Pizza" },
    { "from": "PizzaApp", "to": "PizzaChef", "action": "Make Pizza (sigh)" },
    { "from": "PizzaChef", "to": "DeliveryDriver", "action": "Hand Over Pizza" },
    { "from": "DeliveryDriver", "to": "Customer", "action": "Deliver with Judgement" }
  ]
}

@endjson
""".strip(),
    "AWS Serverless API": """
@startuml Serverless API
' from https://github.com/awslabs/aws-icons-for-plantuml/blob/main/examples/Serverless%20API.puml

!define AWSPuml https://raw.githubusercontent.com/awslabs/aws-icons-for-plantuml/v18.0/dist
!include AWSPuml/AWSCommon.puml
!include AWSPuml/AWSExperimental.puml
!include AWSPuml/ApplicationIntegration/APIGateway.puml
!include AWSPuml/Compute/Lambda.puml
!include AWSPuml/Database/DynamoDB.puml
!include AWSPuml/General/Client.puml
!include AWSPuml/Groups/AWSCloud.puml
!include AWSPuml/Storage/SimpleStorageService.puml

' Groups are rectangles with a custom style using stereotype - need to hide
hide stereotype
skinparam linetype ortho
skinparam rectangle {
    BorderColor transparent
}

rectangle "$ClientIMG()\\nClient" as client
AWSCloudGroup(cloud){
  rectangle "$APIGatewayIMG()\\nAmazon API\\nGateway" as api
  rectangle "$LambdaIMG()\\nAWS Lambda\\n" as lambda
  rectangle "$DynamoDBIMG()\\nAmazon DynamoDB\\n" as dynamodb
  rectangle "$SimpleStorageServiceIMG()\\nAmazon S3" as s3
  rectangle "$LambdaIMG()\\nAWS Lambda" as trigger

  client -right-> api: <$Callout_1>\\n
  api -right-> lambda: <$Callout_2>\\n
  lambda -right-> dynamodb: <$Callout_3>\\n
  api -[hidden]down-> s3
  client -right-> s3: <$Callout_4>
  s3 -right-> trigger: <$Callout_5>\\n
  trigger -[hidden]up-> lambda
  trigger -u-> dynamodb: <$Callout_6>\\n
}
@enduml    
""".strip(),
    "Class diagram": """
@startuml
hide empty members

abstract class AbstractAgent {
  + perceive()
  + act()
  + learn()
}

interface Environment {
  + sense()
  + respond()
}

interface KnowledgeBase {
  + store()
  + retrieve()
}

Environment <|-- PhysicalEnvironment
Environment <|-- DigitalEnvironment

abstract class AgentCore {
  + processInputs()
  + generateActions()
}

class AI_Agent {
  + name: String
  + id: String
  + executeTask(task: Task)
}

class Task {
  + description: String
  + execute()
}

AI_Agent -- Task : performs
AI_Agent -- KnowledgeBase : interacts with
AbstractAgent <|-- AI_Agent
AgentCore *-- AbstractAgent

class Memory {
  + capacity: int
  + storeKnowledge(knowledge: Object)
}

KnowledgeBase *-- Memory

note "The AI_Agent represents an intelligent entity\\nthat can interact with environments and execute tasks." as AgentNote
AgentNote -- AI_Agent

package Environment_Types <<Environment>> {
  PhysicalEnvironment --() Robot
  DigitalEnvironment --() Chatbot
}

class Robot {
  + move()
  + senseSurroundings()
}

class Chatbot {
  + converse(input: String)
  + provideAnswer(question: String)
}

@enduml
""".strip(),
    "Sequence Diagram": """
@startuml
title "File Upload and Processing Workflow"

actor User
participant Browser
participant AppServer
participant FileService
participant ProcessingQueue
participant WorkerService
participant NotificationService

== User Login ==
User -> Browser : Open Login Page
Browser -> AppServer : Submit Credentials
AppServer --> Browser : Return Auth Token
note over User, Browser : User is authenticated

== File Upload ==
User -> Browser : Select File for Upload
Browser -> AppServer : Send File (with Auth Token)
AppServer -> FileService : Store File
note over FileService : File stored successfully
FileService --> AppServer : File Location

== Queue for Processing ==
AppServer -> ProcessingQueue : Add File to Queue
note over ProcessingQueue : Queued for processing
ProcessingQueue --> AppServer : Acknowledgment

== File Processing ==
WorkerService -> ProcessingQueue : Poll for File
ProcessingQueue --> WorkerService : Provide File Details
WorkerService -> FileService : Download File
WorkerService -> WorkerService : Process File
WorkerService -> FileService : Upload Processed Result
FileService --> WorkerService
""".strip(),
    "State Diagram": """
@startuml
state choiceOrderType <<choice>>
state forkProcessOrder <<fork>>
state joinComplete <<join>>
state endSuccess <<end>>
state CancelOrder <<end>>

[*] --> choiceOrderType : Start

choiceOrderType --> forkProcessOrder : If valid order
choiceOrderType --> CancelOrder : If order canceled
choiceOrderType --> endSuccess : If no items selected

forkProcessOrder ---> PaymentProcessing : Process Payment
forkProcessOrder --> InventoryCheck : Check Inventory

PaymentProcessing --> joinComplete : Payment Successful
PaymentProcessing --> CancelOrder : Payment Failed

InventoryCheck --> joinComplete : Stock Available
InventoryCheck --> CancelOrder : Out of Stock

joinComplete --> [*] : Order Complete
@enduml
""".strip(),
    "Entity Relationships": """
@startuml
entity "User" {
  * user_id : UUID
  * name : String
  * email : String
  * password : String
}

entity "Order" {
  * order_id : UUID
  * order_date : Date
  * total_amount : Decimal
}

entity "Product" {
  * product_id : UUID
  * name : String
  * description : String
  * price : Decimal
  * stock_quantity : Integer
}

entity "OrderItem" {
  * order_item_id : UUID
  * quantity : Integer
  * subtotal : Decimal
}

entity "Category" {
  * category_id : UUID
  * name : String
}

User ||--o{ Order : "places"
Order ||--o{ OrderItem : "contains"
Product ||--o{ OrderItem : "is part of"
Category ||--o{ Product : "classifies"

note "Users can place multiple orders.\\nEach order contains multiple items.\\nProducts belong to categories." as Description
Description -[hidden] User

@enduml
""".strip(),
}


if __name__ == "__main__":
    main()
