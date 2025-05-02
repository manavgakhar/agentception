import streamlit as st
import asyncio
import json
from tools.code_tools import CodeAnalysisTool, CodeGenerationTool
from tools.gemini_tools import GeminiTools
from tools.knowledge_tools import KnowledgeTools
from tools.app_manager import AppManager
from tools.code_execution import CodeExecutionTools
from agno.agent import Agent
from agno.models.google.gemini import Gemini
from temporalio.client import Client as TemporalClient
from datetime import datetime
import os
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Initialize tools
code_analyzer = CodeAnalysisTool()
code_generator = CodeGenerationTool()
gemini_tools = GeminiTools()
knowledge_tools = KnowledgeTools()
app_manager = AppManager()
code_executor = CodeExecutionTools()

# Streamlit UI
st.set_page_config(page_title="Agentic App Generator", layout="wide")

# Add tabs for different sections
tab1, tab2, tab3 = st.tabs(["Generate New App", "App Library", "Knowledge Base"])

with tab1:
    st.title("🤖 Agentic App Generator")

    # with st.sidebar:
    #     st.header("About")
    #     st.write("""
    #     This tool helps you create agent-based applications using natural language.
    #     Simply describe what you want your app to do, and we'll generate the code
    #     using ai agents, Temporal workflows, and a Streamlit UI.
    #     """)
        
    #     st.header("Example Prompts")
    #     st.code("""
    # 1. Create a trip planner that checks weather and books flights
    # 2. Build a document analyzer that extracts info and generates summaries
    # 3. Make a social media scheduler with content generation
    #     """)

    # Main input area
    user_prompt = st.text_area(
        "Describe your agentic app requirements:",
        height=150,
        placeholder="Example: I want an app that uses agents to plan trips by checking weather and booking flights..."
    )
    app_name_input = st.text_input("Enter a name for your app:", placeholder="e.g., TripPlanner")

    # Configuration options
    with st.expander("Advanced Configuration"):
        use_temporal = st.checkbox("Use Temporal Workflows", value=False)
        save_and_test_code = st.checkbox("Save and Test Code", value=True)
        include_tests = st.checkbox("Generate Tests", value=False)
        deployment_type = st.selectbox(
            "Deployment Type",
            ["Local", "Docker", "Cloud (AWS)", "Cloud (GCP)"]
        )
        
        # Knowledge base integration
        st.subheader("Knowledge Integration")
        use_knowledge_base = st.checkbox("Use Knowledge Base for Generation", value=False)
        if use_knowledge_base:
            st.info("The app will use the knowledge base to enhance code generation.")

async def generate_app(app_name_from_input: str):
    knowledge_context_str = ""
    # Get relevant knowledge if enabled
    if use_knowledge_base:
        with st.spinner("Searching knowledge base..."):
            knowledge_results = await knowledge_tools.search_knowledge(user_prompt)
            if knowledge_results:
                st.subheader("📚 Relevant Knowledge Found")
                knowledge_items = []
                for result in knowledge_results:
                     # Display the knowledge
                    st.code(result['content'])
                    # Store content for context
                    knowledge_items.append(result['content'])

                # Format knowledge for context
                knowledge_context_str = "\n\n--- Relevant Knowledge Base Content ---\n"
                knowledge_context_str += "\n---\n".join(knowledge_items)
                knowledge_context_str += "\n--------------------------------------\n"

    # Combine user prompt with knowledge context
    final_prompt = user_prompt
    if knowledge_context_str:
        final_prompt = f"{user_prompt}\n{knowledge_context_str}"
        st.info("Knowledge base content has been added to the generation context.")

    print('here')
    print(final_prompt)

    with st.spinner("Analyzing requirements..."):
        # Convert prompt (potentially augmented with knowledge) to specification
        spec_dict = await gemini_tools.analyze_prompt(final_prompt)
        
        # Show specification
        st.subheader("📋 Generated Specification")
        st.code(spec_dict)
        
        # Generate agent code
        with st.spinner("Generating agent code..."):
            agent_code = await gemini_tools.generate_agent_implementation(spec_dict)
            st.subheader("🤖 Agent Implementation")
            st.code(agent_code, language="python")
            
            # Test the generated agent code
            # with st.spinner("Testing agent code..."):
            #     test_result = await code_executor.execute_code(agent_code)
            #     if test_result["success"]:
            #         st.success("Agent code tested successfully!")
            #     else:
            #         st.error(f"Agent code test failed: {test_result['error']}")
        
        # Generate workflow code if enabled
        workflow_code = None
        if use_temporal:
            with st.spinner("Generating workflow code..."):
                workflow_code = await gemini_tools.generate_workflow_implementation(spec_dict)
                st.subheader("🔄 Workflow Implementation")
                st.code(workflow_code, language="python")
        
        # Generate UI code
        with st.spinner("Generating UI code..."):
            ui_code = await code_generator.generate_ui_code(spec_dict, agent_code)
            st.subheader("🎨 UI Implementation")
            st.code(ui_code, language="python")


        if save_and_test_code:
            try:
                app_name = app_name_from_input if app_name_from_input else spec_dict.get("name", "generated_app")
                if not app_name:
                    app_name = "generated_app"
                files = {
                    "app.py": ui_code,
                    "agent.py": agent_code,
                }
                if workflow_code:
                    files["workflow.py"] = workflow_code
                    
                with st.spinner("Saving app..."):
                    app_dir = await app_manager.save_app(
                        name=app_name,
                        description=user_prompt,
                        files=files
                    )
                    st.success(f"App saved successfully to {app_dir}")
                    logging.info(f"App '{app_name}' saved successfully to {app_dir}")
                    
                    # Test the generated code
                    logging.info("Testing the generated agent code...")
                    test_result = await code_executor.execute_code(agent_code)
                    if test_result["success"]:
                        st.success("Agent code tested successfully!")
                        logging.info("Agent code tested successfully.")
                    else:
                        st.error(f"Agent code test failed: {test_result['error']}")
                        logging.error(f"Agent code test failed: {test_result['error']}")
                        if test_result.get("fixed_code"):
                            st.warning("Generated fixed version of the code:")
                            st.code(test_result["fixed_code"], language="python")
                            agent_code = test_result["fixed_code"]
                            files["agent.py"] = agent_code
                            await app_manager.save_app(
                                name=app_name,
                                description=user_prompt,
                                files=files
                            )
                            logging.info(f"Fixed version of agent code saved for app '{app_name}'.")

                    # Try running the Streamlit UI
                    logging.info("Starting Streamlit UI...")
                    ui_result = await code_executor.run_streamlit_app(ui_code)
                    if ui_result["success"]:
                        st.success("Streamlit UI is running!")
                        logging.info("Streamlit UI is running successfully.")
                        st.info("Check your terminal for the Streamlit URL")
                    else:
                        st.error(f"Failed to start Streamlit UI: {ui_result['error']}")
                        logging.error(f"Failed to start Streamlit UI: {ui_result['error']}")
                    
            except Exception as e:
                st.error(f"Failed to save/test app: {str(e)}")
                logging.error(f"Failed to save/test app: {str(e)}")
                st.stop()
        
        # Show next steps
        st.subheader("🚀 Next Steps")
        st.write("""
        1. Copy the generated code to your project
        2. Install required dependencies
        3. Set up environment variables
        4. Run the application
        """)
        
        # Download options
        col1, col2, col3 = st.columns(3)
        with col1:
            st.download_button(
                "Download Agent Code",
                agent_code,
                file_name="agent_code.py",
                mime="text/plain"
            )
        with col2:
            if workflow_code:
                st.download_button(
                    "Download Workflow Code",
                    workflow_code,
                    file_name="workflow_code.py",
                    mime="text/plain"
                )
        with col3:
            st.download_button(
                "Download UI Code",
                ui_code,
                file_name="ui_code.py",
                mime="text/plain"
            )

    

with tab2:
    st.title("📚 App Library")
    
    # Add a refresh button
    if st.button("🔄 Refresh Library"):
        app_manager.load_library()
        st.rerun()
    
    # Display saved apps
    try:
        apps = app_manager.get_app_library()
        
        if not apps:
            st.info("No apps saved yet. Generate your first app in the 'Generate New App' tab!")
        else:
            st.success(f"Found {len(apps)} saved apps")
            for app in apps:
                with st.expander(f"{app['name']} - {app['created_at']}"):
                    st.write(f"**Description:** {app['description']}")
                    st.write(f"**Location:** {app['path']}")
                    st.write("**Files:**")
                    
                    # Show files with view buttons
                    for file in app['files']:
                        col1, col2 = st.columns([3, 1])
                        with col1:
                            st.code(file)
                        with col2:
                            if st.button(f"View", key=f"view_{app['name']}_{file}"):
                                try:
                                    with open(os.path.join(app['path'], file), 'r') as f:
                                        content = f.read()
                                        st.code(content, language="python")
                                except Exception as e:
                                    st.error(f"Error reading {file}: {str(e)}")
                    
                    # Add delete button
                    if st.button(f"Delete App", key=f"delete_{app['name']}"):
                        try:
                            # Remove the app directory
                            import shutil
                            shutil.rmtree(app['path'])
                            
                            # Remove from library
                            app_manager.library['apps'].remove(app)
                            app_manager.save_library()
                            
                            st.success(f"Deleted {app['name']}")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error deleting app: {str(e)}")
    except Exception as e:
        st.error(f"Error loading app library: {str(e)}")

with tab3:
    st.title("🧠 Knowledge Base")
    
    # Add new knowledge
    st.header("Add Knowledge")
    knowledge_content = st.text_area(
        "Enter knowledge content:",
        height=150,
        placeholder="Enter code snippets, documentation, or other knowledge to store..."
    )
    
    knowledge_type = st.selectbox(
        "Knowledge Type",
        ["Code Snippet", "Documentation", "Example", "Best Practice"]
    )
    
    if st.button("Add to Knowledge Base"):
        if knowledge_content:
            asyncio.run(knowledge_tools.add_document(
                content=knowledge_content,
                metadata={
                    "type": knowledge_type,
                    "added_at": datetime.now().isoformat()
                }
            ))
            st.success("Knowledge added successfully!")
        else:
            st.error("Please enter content to add to the knowledge base.")
    
    # Search knowledge
    st.header("Search Knowledge")
    search_query = st.text_input("Search query:")
    if search_query:
        results = asyncio.run(knowledge_tools.search_knowledge(search_query))
        for result in results:
            with st.expander(f"Result (Similarity: {result['similarity']:.2f})"):
                st.write("**Content:**")
                st.code(result['content'])
                st.write("**Metadata:**")
                st.json(result['metadata'])

if tab1.button("🚀 Generate App"):
    if user_prompt:
        asyncio.run(generate_app(app_name_input))
    else:
        st.error("Please enter your app requirements first!") 