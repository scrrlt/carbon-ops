## Summary

Brief description of the changes in this pull request.

## Type of Change

Please check the relevant options:

- [ ] Bug fix (non-breaking change which fixes an issue)
- [ ] New feature (non-breaking change which adds functionality)
- [ ] Breaking change (fix or feature that would cause existing functionality to not work as expected)
- [ ] Documentation update (changes to documentation only)
- [ ] Code cleanup/refactoring (no functional changes)
- [ ] Performance improvement
- [ ] Security fix
- [ ] Test addition or improvement
- [ ] Build/CI improvement

## Changes Made

Describe the changes made in detail:

- Change 1
- Change 2
- Change 3

## Testing

Describe how the changes have been tested:

- [ ] Unit tests added/updated
- [ ] Integration tests added/updated
- [ ] Manual testing performed
- [ ] All existing tests pass
- [ ] New tests cover edge cases

**Test Environment:**
- OS: [e.g., Windows 11, Ubuntu 22.04]
- Python version: [e.g., 3.10.8]
- Dependencies: [list any specific versions if relevant]

## Documentation

- [ ] Code is self-documenting with clear variable/function names
- [ ] Docstrings added/updated for new public APIs
- [ ] README.md updated (if applicable)
- [ ] CHANGELOG.md updated
- [ ] Examples updated/added (if applicable)

## Breaking Changes

If this is a breaking change, describe:

1. **What breaks:** What existing functionality will no longer work?
2. **Migration path:** How should users update their code?
3. **Deprecation:** Are there any deprecation warnings in place?

```python
# Example of old usage that will break
old_way = SomeClass(old_parameter=True)

# Example of new usage
new_way = SomeClass(new_parameter=True)
```

## Related Issues

Closes #[issue number]
Relates to #[issue number]
Fixes #[issue number]

## Additional Context

Add any other context about the pull request here:

- Performance implications
- Backwards compatibility considerations
- Alternative approaches considered
- Future work that builds on this chang

## Checklist

### Pre-submission

- [ ] I have read the [contributing guidelines](CONTRIBUTING.md)
- [ ] I have performed a self-review of my own code
- [ ] I have commented my code, particularly in hard-to-understand areas
- [ ] I have made corresponding changes to the documentation
- [ ] My changes generate no new warnings
- [ ] I have added tests that prove my fix is effective or that my feature works
- [ ] New and existing unit tests pass locally with my changes
- [ ] Any dependent changes have been merged and published in downstream modules

### Security (if applicable)

- [ ] I have not committed any secrets or sensitive data
- [ ] I have followed secure coding practices
- [ ] I have considered security implications of my changes

### Performance (if applicable)

- [ ] I have considered the performance impact of my changes
- [ ] I have benchmarked critical paths (if performance sensitive)
- [ ] Memory usage has been considered

## Reviewer Notes

Any specific areas you'd like reviewers to focus on:

- [ ] Algorithm correctness
- [ ] Error handling
- [ ] Performance implications
- [ ] API design
- [ ] Documentation clarity
- [ ] Test coverage

**Questions for reviewers:**
1. Question 1?
2. Question 2?
