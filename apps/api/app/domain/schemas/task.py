"""Task 科研工作单元对象契约。

仅定义科研工作单元的最小 Pydantic 校验模型：任务标题与说明、
所属 Project、指派者与执行者引用、输入对象版本引用、
期望输出对象类型、任务状态、截止时间与优先级。
不包含队列任务、异步调度、Agent 自动执行记录或任务完成后的
Memory 写入逻辑。
"""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

from .common import ObjectReference, ObjectType, TaskStatus


class Task(BaseModel):
    """科研工作单元对象：固定指派关系、输入对象版本、期望输出类型与任务状态。

    表达任务标题与说明、所属 Project、指派者与执行者引用、
    输入对象版本引用、期望输出对象类型、任务状态、截止时间与优先级；
    不表达队列任务、异步调度、Agent 自动执行记录或任务完成后的
    Memory 写入。
    """

    title: Annotated[str, StringConstraints(min_length=1, strip_whitespace=True)]  # 任务标题
    project: ObjectReference  # 所属 Project
    expected_output_object_type: ObjectType  # 期望输出对象类型
    status: TaskStatus  # 任务状态
    description: str | None = None  # 任务说明
    assigner: ObjectReference | None = None  # 指派者引用
    assignee: ObjectReference | None = None  # 执行者引用
    input_versions: list[ObjectReference] = Field(default_factory=list)  # 输入对象版本引用
    deadline: datetime | None = None  # 截止时间
    priority: str | None = None  # 优先级
