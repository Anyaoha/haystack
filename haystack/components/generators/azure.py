# SPDX-FileCopyrightText: 2022-present deepset GmbH <info@deepset.ai>
#
# SPDX-License-Identifier: Apache-2.0

import os
from typing import Any, Callable, Dict, Optional

from openai.lib.azure import AzureADTokenProvider, AzureOpenAI

from haystack import component, default_from_dict, default_to_dict
from haystack.components.generators import OpenAIGenerator
from haystack.dataclasses import StreamingChunk
from haystack.utils import Secret, deserialize_callable, deserialize_secrets_inplace, serialize_callable


@component
class AzureOpenAIGenerator(OpenAIGenerator):
    """
    Generates text using OpenAI's large language models (LLMs).

    It works with the gpt-4 - type models and supports streaming responses
    from OpenAI API.

    You can customize how the text is generated by passing parameters to the
    OpenAI API. Use the `**generation_kwargs` argument when you initialize
    the component or when you run it. Any parameter that works with
    `openai.ChatCompletion.create` will work here too.


    For details on OpenAI API parameters, see
    [OpenAI documentation](https://platform.openai.com/docs/api-reference/chat).


    ### Usage example

    ```python
    from haystack.components.generators import AzureOpenAIGenerator
    from haystack.utils import Secret
    client = AzureOpenAIGenerator(
        azure_endpoint="<Your Azure endpoint e.g. `https://your-company.azure.openai.com/>",
        api_key=Secret.from_token("<your-api-key>"),
        azure_deployment="<this a model name, e.g.  gpt-4o-mini>")
    response = client.run("What's Natural Language Processing? Be brief.")
    print(response)
    ```

    ```
    >> {'replies': ['Natural Language Processing (NLP) is a branch of artificial intelligence that focuses on
    >> the interaction between computers and human language. It involves enabling computers to understand, interpret,
    >> and respond to natural human language in a way that is both meaningful and useful.'], 'meta': [{'model':
    >> 'gpt-4o-mini', 'index': 0, 'finish_reason': 'stop', 'usage': {'prompt_tokens': 16,
    >> 'completion_tokens': 49, 'total_tokens': 65}}]}
    ```
    """

    # pylint: disable=super-init-not-called
    def __init__(  # pylint: disable=too-many-positional-arguments
        self,
        azure_endpoint: Optional[str] = None,
        api_version: Optional[str] = "2023-05-15",
        azure_deployment: Optional[str] = "gpt-4o-mini",
        api_key: Optional[Secret] = Secret.from_env_var("AZURE_OPENAI_API_KEY", strict=False),
        azure_ad_token: Optional[Secret] = Secret.from_env_var("AZURE_OPENAI_AD_TOKEN", strict=False),
        organization: Optional[str] = None,
        streaming_callback: Optional[Callable[[StreamingChunk], None]] = None,
        system_prompt: Optional[str] = None,
        timeout: Optional[float] = None,
        max_retries: Optional[int] = None,
        generation_kwargs: Optional[Dict[str, Any]] = None,
        default_headers: Optional[Dict[str, str]] = None,
        *,
        azure_ad_token_provider: Optional[AzureADTokenProvider] = None,
    ):
        """
        Initialize the Azure OpenAI Generator.

        :param azure_endpoint: The endpoint of the deployed model, for example `https://example-resource.azure.openai.com/`.
        :param api_version: The version of the API to use. Defaults to 2023-05-15.
        :param azure_deployment: The deployment of the model, usually the model name.
        :param api_key: The API key to use for authentication.
        :param azure_ad_token: [Azure Active Directory token](https://www.microsoft.com/en-us/security/business/identity-access/microsoft-entra-id).
        :param organization: Your organization ID, defaults to `None`. For help, see
        [Setting up your organization](https://platform.openai.com/docs/guides/production-best-practices/setting-up-your-organization).
        :param streaming_callback: A callback function called when a new token is received from the stream.
            It accepts [StreamingChunk](https://docs.haystack.deepset.ai/docs/data-classes#streamingchunk)
            as an argument.
        :param system_prompt: The system prompt to use for text generation. If not provided, the Generator
        omits the system prompt and uses the default system prompt.
        :param timeout: Timeout for AzureOpenAI client. If not set, it is inferred from the
            `OPENAI_TIMEOUT` environment variable or set to 30.
        :param max_retries: Maximum retries to establish contact with AzureOpenAI if it returns an internal error.
            If not set, it is inferred from the `OPENAI_MAX_RETRIES` environment variable or set to 5.
        :param generation_kwargs: Other parameters to use for the model, sent directly to
            the OpenAI endpoint. See [OpenAI documentation](https://platform.openai.com/docs/api-reference/chat) for
            more details.
            Some of the supported parameters:
            - `max_tokens`: The maximum number of tokens the output text can have.
            - `temperature`: The sampling temperature to use. Higher values mean the model takes more risks.
                Try 0.9 for more creative applications and 0 (argmax sampling) for ones with a well-defined answer.
            - `top_p`: An alternative to sampling with temperature, called nucleus sampling, where the model
                considers the results of the tokens with top_p probability mass. For example, 0.1 means only the tokens
                comprising the top 10% probability mass are considered.
            - `n`: The number of completions to generate for each prompt. For example, with 3 prompts and n=2,
                the LLM will generate two completions per prompt, resulting in 6 completions total.
            - `stop`: One or more sequences after which the LLM should stop generating tokens.
            - `presence_penalty`: The penalty applied if a token is already present.
                Higher values make the model less likely to repeat the token.
            - `frequency_penalty`: Penalty applied if a token has already been generated.
                Higher values make the model less likely to repeat the token.
            - `logit_bias`: Adds a logit bias to specific tokens. The keys of the dictionary are tokens, and the
                values are the bias to add to that token.
        :param default_headers: Default headers to use for the AzureOpenAI client.
        :param azure_ad_token_provider: A function that returns an Azure Active Directory token, will be invoked on
            every request.
        """
        # We intentionally do not call super().__init__ here because we only need to instantiate the client to interact
        # with the API.

        # Why is this here?
        # AzureOpenAI init is forcing us to use an init method that takes either base_url or azure_endpoint as not
        # None init parameters. This way we accommodate the use case where env var AZURE_OPENAI_ENDPOINT is set instead
        # of passing it as a parameter.
        azure_endpoint = azure_endpoint or os.environ.get("AZURE_OPENAI_ENDPOINT")
        if not azure_endpoint:
            raise ValueError("Please provide an Azure endpoint or set the environment variable AZURE_OPENAI_ENDPOINT.")

        if api_key is None and azure_ad_token is None:
            raise ValueError("Please provide an API key or an Azure Active Directory token.")

        # The check above makes mypy incorrectly infer that api_key is never None,
        # which propagates the incorrect type.
        self.api_key = api_key  # type: ignore
        self.azure_ad_token = azure_ad_token
        self.generation_kwargs = generation_kwargs or {}
        self.system_prompt = system_prompt
        self.streaming_callback = streaming_callback
        self.api_version = api_version
        self.azure_endpoint = azure_endpoint
        self.azure_deployment = azure_deployment
        self.organization = organization
        self.model: str = azure_deployment or "gpt-4o-mini"
        self.timeout = timeout if timeout is not None else float(os.environ.get("OPENAI_TIMEOUT", "30.0"))
        self.max_retries = max_retries if max_retries is not None else int(os.environ.get("OPENAI_MAX_RETRIES", "5"))
        self.default_headers = default_headers or {}
        self.azure_ad_token_provider = azure_ad_token_provider

        self.client = AzureOpenAI(
            api_version=api_version,
            azure_endpoint=azure_endpoint,
            azure_deployment=azure_deployment,
            azure_ad_token_provider=azure_ad_token_provider,
            api_key=api_key.resolve_value() if api_key is not None else None,
            azure_ad_token=azure_ad_token.resolve_value() if azure_ad_token is not None else None,
            organization=organization,
            timeout=self.timeout,
            max_retries=self.max_retries,
            default_headers=self.default_headers,
        )

    def to_dict(self) -> Dict[str, Any]:
        """
        Serialize this component to a dictionary.

        :returns:
            The serialized component as a dictionary.
        """
        callback_name = serialize_callable(self.streaming_callback) if self.streaming_callback else None
        azure_ad_token_provider_name = None
        if self.azure_ad_token_provider:
            azure_ad_token_provider_name = serialize_callable(self.azure_ad_token_provider)
        return default_to_dict(
            self,
            azure_endpoint=self.azure_endpoint,
            azure_deployment=self.azure_deployment,
            organization=self.organization,
            api_version=self.api_version,
            streaming_callback=callback_name,
            generation_kwargs=self.generation_kwargs,
            system_prompt=self.system_prompt,
            api_key=self.api_key.to_dict() if self.api_key is not None else None,
            azure_ad_token=self.azure_ad_token.to_dict() if self.azure_ad_token is not None else None,
            timeout=self.timeout,
            max_retries=self.max_retries,
            default_headers=self.default_headers,
            azure_ad_token_provider=azure_ad_token_provider_name,
        )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AzureOpenAIGenerator":
        """
        Deserialize this component from a dictionary.

        :param data:
            The dictionary representation of this component.
        :returns:
            The deserialized component instance.
        """
        deserialize_secrets_inplace(data["init_parameters"], keys=["api_key", "azure_ad_token"])
        init_params = data.get("init_parameters", {})
        serialized_callback_handler = init_params.get("streaming_callback")
        if serialized_callback_handler:
            data["init_parameters"]["streaming_callback"] = deserialize_callable(serialized_callback_handler)
        serialized_azure_ad_token_provider = init_params.get("azure_ad_token_provider")
        if serialized_azure_ad_token_provider:
            data["init_parameters"]["azure_ad_token_provider"] = deserialize_callable(
                serialized_azure_ad_token_provider
            )
        return default_from_dict(cls, data)
