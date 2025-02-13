import json
import os
from typing import Any, Dict, List
import re

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, SystemMessage, HumanMessage
from langchain_core.tools import BaseTool
from langchain_core.runnables import Runnable
from langchain_gigachat import GigaChat
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, ValidationError

from protollm.connectors.utils import (get_access_token,
                                       models_without_function_calling,
                                       models_without_structured_output)
from protollm.definitions import CONFIG_PATH


load_dotenv(CONFIG_PATH)


class CustomChatOpenAI(ChatOpenAI):
    """
    A class that extends the ChatOpenAI base class to allow use with the LLama family of models, as they do not return
    tool calls in the tool_calls field of the response, but instead write them as an HTML string in the content field.
    """

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self._response_format = None
        self._tool_choice_mode = None
        self._tools = None

    def invoke(self, messages: str | list, *args, **kwargs) -> AIMessage | dict | BaseModel:
        if self._requires_custom_handling_for_tools() and self._tools:
            system_prompt = self._generate_system_prompt_with_tools()
            # Add a system prompt with function description if it's not presented
            if self._tools and isinstance(messages, str):
                tmp = messages
                messages = [SystemMessage(content=system_prompt), HumanMessage(content=tmp)]
            elif self._tools and not any(isinstance(msg, SystemMessage) for msg in messages):
                messages.insert(0, SystemMessage(content=system_prompt))
            # If the system prompt is already in the list of messages, expand it with a description of the tools
            else:
                idx = 0
                for index, obj in enumerate(messages):
                    if isinstance(obj, SystemMessage):
                        idx = index
                        break
                messages[idx].content += "\n\n" + system_prompt
                
        if self._requires_custom_handling_for_structured_output() and self._response_format:
            system_prompt = self._generate_system_prompt_with_schema()
            # Add a system prompt with function description if it's not presented
            if self._response_format and isinstance(messages, str):
                tmp = messages
                messages = [SystemMessage(content=system_prompt), HumanMessage(content=tmp)]
            elif self._response_format and not any(isinstance(msg, SystemMessage) for msg in messages):
                messages.insert(0, SystemMessage(content=system_prompt))
            # If the system prompt is already in the list of messages, expand it with a description of the tools
            else:
                idx = 0
                for index, obj in enumerate(messages):
                    if isinstance(obj, SystemMessage):
                        idx = index
                        break
                messages[idx].content += "\n\n" + system_prompt

        response = super().invoke(messages, *args, **kwargs)

        if isinstance(response, AIMessage) and response.content.startswith("<function="):
            tool_calls = self._parse_function_calls(response.content)
            if tool_calls:
                response.tool_calls = tool_calls
                response.content = ""

        if isinstance(response, AIMessage) and self._response_format:
            response = self._parse_custom_structure(response)

        return response

    def bind_tools(self, *args, **kwargs: Any) -> Runnable:
        if self._requires_custom_handling_for_tools():
            self._tools = kwargs.get("tools", [])
            self._tool_choice_mode = kwargs.get("tool_choice", "auto")
            return self
        else:
            return super().bind_tools(*args, **kwargs)
        
    def with_structured_output(self, *args, **kwargs: Any) -> Runnable:
        if self._requires_custom_handling_for_structured_output():
            self._response_format = kwargs.get("schema", [])
            return self
        else:
            return super().with_structured_output(*args, **kwargs)

    def _generate_system_prompt_with_tools(self) -> str:
        """
        Generates a system prompt with function descriptions and instructions for the model.
        """
        tool_descriptions = []
        for tool in self._tools:
            if isinstance(tool, dict):
                tool_descriptions.append(
                    f"Function name: {tool['name']}\n"
                    f"Description: {tool['description']}\n"
                    f"Parameters: {json.dumps(tool['parameters'], ensure_ascii=False)}"
                )
            elif isinstance(tool, BaseTool):
                tool_descriptions.append(
                    f"Function name: {tool.name}\n"
                    f"Description: {tool.description}\n"
                    f"Parameters: {json.dumps(tool.args, ensure_ascii=False)}")
            else:
                raise ValueError(
                    "Unsupported tool type. Try using a dictionary or function with the @tool decorator as tools"
                )
        tool_prefix = "You have access to the following functions:\n\n"
        tool_instructions = (
            "If you choose to call a function ONLY reply in the following format with no prefix or suffix:\n"
            '<function=example_function_name>{"example_name": "example_value"}</function>'
        )
        return tool_prefix + "\n\n".join(tool_descriptions) + "\n\n" + tool_instructions
    
    def _generate_system_prompt_with_schema(self) -> str:
        """
        Generates a system prompt with response format descriptions and instructions for the model.
        """
        schema_descriptions = []
        for schema in [self._response_format]:
            if isinstance(schema, dict):
                schema_descriptions.append(str(schema))
            elif issubclass(schema, BaseModel):
                schema_descriptions.append(str(schema.model_json_schema()))
            else:
                raise ValueError(
                    "Unsupported schema type. Try using a description of the answer structure as a dictionary or"
                    " Pydantic model."
                )
        schema_prefix = "Generate a JSON object that matches one of the following schemas:\n\n"
        schema_instructions = (
            "Your response must contain ONLY valid JSON, parsable by a standard JSON parser. Do not include any"
            " additional text, explanations, or comments."
        )
        return schema_prefix + "\n\n".join(schema_descriptions) + "\n\n" + schema_instructions

    def _requires_custom_handling_for_tools(self) -> bool:
        """
        Determines whether additional processing for tool calling is required for the current model.
        """
        return any(model_name in self.model_name.lower() for model_name in models_without_function_calling)
    
    def _requires_custom_handling_for_structured_output(self) -> bool:
        """
        Determines whether additional processing for structured output is required for the current model.
        """
        return any(model_name in self.model_name.lower() for model_name in models_without_structured_output)
    
    def _parse_custom_structure(self, response_from_model) -> dict | BaseModel:
        """
        Parses the model response into a dictionary or Pydantic class
        
        Args:
            response_from_model: response of a model that does not support structured output by default
        
        Raises:
            Error if a structured response is not obtained
        """
        if isinstance([self._response_format][0], dict):
            try:
                resp = json.loads(response_from_model.content)
                return resp
            except Exception as e:
                print(e)
        elif issubclass([self._response_format][0], BaseModel):
            for schema in [self._response_format]:
                try:
                    resp = schema.model_validate_json(response_from_model.content)
                    return resp
                except ValidationError:
                    continue
            raise Exception("Failed to return structured output.")
        
    @staticmethod
    def _parse_function_calls(content: str) -> List[Dict[str, Any]]:
        """
        Parses LLM answer (HTML string) to extract function calls.

        Args:
            content: model response as an HTML string

        Returns:
            A list of dictionaries in tool_calls format/
        """
        tool_calls = []
        pattern = r"<function=(.*?)>(.*?)</function>"
        matches = re.findall(pattern, content, re.DOTALL)

        for match in matches:
            function_name, function_args = match
            try:
                arguments = json.loads(function_args)
            except json.JSONDecodeError as e:
                raise ValueError(f"Error when decoding function arguments: {e}")

            tool_call = {
                "id": f"call_{len(tool_calls) + 1}",
                "type": "tool_call",
                "name": function_name,
                "args": arguments
            }
            tool_calls.append(tool_call)

        return tool_calls


def create_llm_connector(model_url: str, *args: Any, **kwargs: Any) -> CustomChatOpenAI | GigaChat:
    """Creates the proper connector for a given LLM service URL.

    Args:
        model_url: The LLM endpoint for making requests; should be in the format 'base_url;model_endpoint or name'
            - for vsegpt.ru service for example: 'https://api.vsegpt.ru/v1;meta-llama/llama-3.1-70b-instruct'
            - for Gigachat models family: 'https://gigachat.devices.sberbank.ru/api/v1/chat/completions;Gigachat'
              for Gigachat model you should also install certificates from 'НУЦ Минцифры' -
              instructions - 'https://developers.sber.ru/docs/ru/gigachat/certificates'

    Returns:
        The ChatModel object from 'langchain' that can be used to make requests to the LLM service,
        use tools, get structured output.
    """
    if "vsegpt" in model_url:
        model_data = model_url.split(";")
        base_url, model_name = model_data[0], model_data[1]
        api_key = os.getenv("VSE_GPT_KEY")
        return CustomChatOpenAI(model_name=model_name, base_url=base_url, api_key=api_key, *args, **kwargs)
    elif "gigachat":
        model_name = model_url.split(";")[1]
        access_token = get_access_token()
        return GigaChat(model=model_name, access_token=access_token, *args, **kwargs)
    # Possible to add another LangChain compatible connector
