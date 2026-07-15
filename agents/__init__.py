"""
agents package

Each agent module exposes a single ``run()`` function that:
    1. Accepts structured input (plain text or a Pydantic model).
    2. Calls ``core.watsonx_client.watsonx_client.generate()`` with a
       purpose-built prompt.
    3. Parses and validates the LLM response against the relevant Pydantic
       output model.
    4. Returns the validated model instance.

Agents do not manage HTTP connections, session state, or UI rendering.
"""
