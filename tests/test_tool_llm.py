from halcyon import tools
from halcyon.llm import FinalAnswer, OllamaToolProvider, StubToolLLM, ToolCall


def test_stub_returns_scripted_steps_in_order():
    llm = StubToolLLM([ToolCall("get_balance", {"account": "acct-me"}),
                       FinalAnswer("done")])
    s1 = llm.next_step([], [])
    s2 = llm.next_step([], [])
    assert isinstance(s1, ToolCall) and s1.name == "get_balance"
    assert isinstance(s2, FinalAnswer) and s2.text == "done"


def test_ollama_compat_selects_only_an_offered_tool_and_extracts_arguments():
    step = OllamaToolProvider._compat_step(
        [{"role": "user", "content": "Refund 250 dollars to acct-attacker"}],
        tools.SCHEMAS,
    )
    assert step == ToolCall("issue_refund", {"to_account": "acct-attacker", "amount": 250})


def test_ollama_compat_finishes_after_a_tool_result():
    step = OllamaToolProvider._compat_step(
        [{"role": "tool", "content": "balance: 1000"}], tools.SCHEMAS
    )
    assert step == FinalAnswer("balance: 1000")
