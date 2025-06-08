# Mistake #037: N+1 Query Problems

## Problem
Making too many database queries in loops.

### Bad Example
```python
# BAD - N+1 queries
def get_user_posts():
    users = get_all_users()
    for user in users:
        user.posts = get_posts_for_user(user.id)  # N queries
    return users

# GOOD - Batch loading
def get_user_posts():
    users = get_all_users()
    user_ids = [u.id for u in users]
    all_posts = get_posts_for_users(user_ids)  # 1 query
    # Group posts by user
    return users

```

## Solution


## Lesson Learned
Always consider query optimization in database operations.

---
