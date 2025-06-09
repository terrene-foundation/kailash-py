# Connection Patterns

## Basic Connection
```python
workflow.connect("node1", "node2", mapping={"data": "data"})
```

## Named Ports
```python
workflow.connect("node1", "node2", mapping={"processed": "data"})
```

## Multiple Outputs
```python
# SwitchNode node with multiple outputs (each output is mapped)
workflow.connect("switch", "handler1", mapping={"case1": "input"})
workflow.connect("switch", "handler2", mapping={"case2": "input"})
workflow.connect("switch", "default_handler", mapping={"default": "input"})
```

## Merging Inputs
```python
# MergeNode node with multiple inputs
workflow.connect("source1", "merge", mapping={"data": "input1"})
workflow.connect("source2", "merge", mapping={"data": "input2"})
workflow.connect("source3", "merge", mapping={"data": "input3"})
```
