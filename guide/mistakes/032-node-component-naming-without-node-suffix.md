# Mistake #032: Node Component Naming Without "Node" Suffix

## Problem
Using aliases to hide the "Node" suffix makes it unclear to users what type of component they're working with.

### Bad Example
```python
# BAD - Hiding the Node suffix with aliases
@register_node(alias="RESTClient")
class RESTClientNode(Node):
    pass

# Usage becomes confusing
client = RESTClient()  # Is this a Node? A client library? A helper class?

# GOOD - Keep Node in the name
@register_node()
class RESTClientNode(Node):
    pass

# Usage is clear
client = RESTClientNode()  # Obviously a Node component

```

## Solution
Removed all aliases that hide the "Node" suffix. All Node components must include "Node" in their name.
**Principle**: Component type should be immediately clear from the name. Node components should always have "Node" in the name.

## Impact
Users were confused about whether they were using a Node component or some other type of object.

## Fixed In
Session 34 - REST client consolidation

## Categories
workflow

---
