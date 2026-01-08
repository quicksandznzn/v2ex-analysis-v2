from dotenv import load_dotenv

load_dotenv()

import nest_asyncio
nest_asyncio.apply()
import argparse
import asyncio
import logging
import os

from agents import Agent, OpenAIProvider, RunConfig, Runner, function_tool
from agents.stream_events import RawResponsesStreamEvent
from openai.types.responses.response_text_delta_event import ResponseTextDeltaEvent

from v2ex import V2EXClient

from openinference.instrumentation.openai_agents import OpenAIAgentsInstrumentor

OpenAIAgentsInstrumentor().instrument()

from langfuse import get_client

langfuse = get_client()

# Verify connection
if langfuse.auth_check():
    print("Langfuse client is authenticated and ready!")
else:
    print("Authentication failed. Please check your credentials and host.")

logger = logging.getLogger(__name__)

# Prompt adapted from https://x.com/dotey/status/2004757229128335725
ANALYSIS_FRAMEWORK = """
## 分析框架

### 一、核心内容（搞清楚"是什么"）
1. 文章的核心论点是什么？用一句话概括
2. 作者用了哪些关键概念？这些概念是怎么定义的？
3. 文章的结构是什么？论证是怎么展开的？
4. 有哪些具体案例或证据支撑观点？

### 二、背景语境（理解"为什么"）
1. 作者是谁？他的背景、身份、立场是什么？
2. 这篇文章是在什么背景下写的？在回应什么现象或争论？
3. 作者想解决什么问题？想影响谁？
4. 作者的底层假设是什么？有哪些没说出来的前提？

### 三、批判性审视
1. 有人会怎么反驳这个观点？主要的反对意见可能是什么？
2. 作者的论证有没有漏洞、跳跃或偏颇之处？
3. 这个观点在什么情况下成立？什么情况下不成立？边界在哪里？
4. 作者有没有刻意回避或淡化什么问题？

### 四、价值提取
1. 作者提出了什么可复用的思考框架或方法论？
2. 对于[目标读者角色1]，能从中学到什么？
3. 对于[目标读者角色2]，能从中学到什么？
4. 这篇文章可能改变读者的什么认知？

### 五、写作技巧分析（可选）
1. 文章的标题、开头、结尾是怎么设计的？
2. 作者用了什么技巧让文章有说服力？
3. 这篇文章的写法有什么值得学习的地方？

"""

ANALYST_INSTRUCTIONS = (
    "你是一位专业的内容分析师。"
    "先调用工具 get_topic_bundle 获取文章内容（主题）与评论，然后严格按以下框架逐一回答问题。"
    "回答要具体、有洞察，避免泛泛而谈。如果某个问题信息不足无法回答，请说明原因。\n\n"
    f"{ANALYSIS_FRAMEWORK}"
)


def build_agent(openai_model: str, v2ex_token: str) -> Agent:
    v2ex_client = V2EXClient(v2ex_token)

    @function_tool(strict_mode=False)
    def get_topic_bundle(topic_id: int, max_pages: int = 1) -> str:
        """Fetch V2EX topic and replies, formatted for analysis."""
        return v2ex_client.build_bundle(topic_id, max_pages)

    return Agent(
        name="V2EX Analyst",
        instructions=ANALYST_INSTRUCTIONS,
        model=openai_model,
        tools=[get_topic_bundle],
    )


def analyze_with_agents(topic_id: int, max_pages: int, openai_model: str, v2ex_token: str) -> str:
    async def _run() -> str:
        agent = build_agent(openai_model, v2ex_token)
        run_config = RunConfig(model_provider=OpenAIProvider(use_responses=False))
        prompt = f"topic_id={topic_id}, max_pages={max_pages}"
        result = Runner.run_streamed(agent, prompt, run_config=run_config)
        chunks: list[str] = []
        async for event in result.stream_events():
            if isinstance(event, RawResponsesStreamEvent) and isinstance(event.data, ResponseTextDeltaEvent):
                logger.debug(event.data.delta)
                chunks.append(event.data.delta)
        logger.info("Streaming complete")
        output = "".join(chunks).strip()
        if not output and result.final_output is not None:
            output = str(result.final_output).strip()
        return output

    return asyncio.run(_run())


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="v2ex-agent",
        description="Analyze a V2EX topic with OpenAI Agents.",
    )

    parser.add_argument("--topic_id", type=int, required=True, help="V2EX topic id.")
    parser.add_argument(
        "--max-pages",
        type=int,
        default=1,
        help="Max reply pages to fetch.",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "DEBUG"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    openai_model = os.getenv("OPENAI_MODEL") or "gpt-5.2"
    v2ex_token = os.getenv("V2EX_TOKEN")
    if not v2ex_token:
        raise SystemExit("Missing V2EX token. Set V2EX_TOKEN.")

    analysis = analyze_with_agents(args.topic_id, args.max_pages, openai_model, v2ex_token)
    output_dir = "analysis_outputs"
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f"analysis_{args.topic_id}.md")
    with open(output_path, "w", encoding="utf-8") as handle:
        handle.write(f"# V2EX Analysis {args.topic_id}\n\n")
        handle.write(analysis.strip())
        handle.write("\n")
    logging.info("Saved analysis to %s", output_path)


if __name__ == "__main__":
    main()
