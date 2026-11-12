"""组件面荷载。

dead、wind、snow 各自提供计算公式，并可由 build(design_case, trace) 写成荷载工况。
code_loads 按规范提供给模型调用的工具：windASCE16、snowASCE16、windEN1991、snowEN1991，以及两本规范共用的 moduleDead。
"""
