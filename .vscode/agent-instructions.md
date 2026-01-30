# Agent Instructions for GitHub Copilot

These instructions guide autonomous agents working on the lha-memoirs project.

## Core Requirements

### Always Verify Your Work

**Before completing any task, you MUST run the verification commands:**

```bash
npx prettier --write .
npm run test:all
```

These commands run:

- Code formatting (Prettier)
- Linting checks (ESLint)
- Type checking (TypeScript)
- All unit and integration tests

**Do not consider work complete until these commands pass without errors.** If errors occur, fix them and re-run until the commands succeed.

### Use Subagents for Normal to Complex Tasks

When faced with multi-step tasks, **Use the `runSubagent` tool to delegate the task** rather than attempting it yourself. This allows:

- Parallel investigation of independent concerns
- Focused expertise on specific subtasks
- Better resource utilization
- Cleaner separation of concerns

## Project Conventions

### TypeScript & Code Quality

- Use strict TypeScript (`skipLibCheck=false`, no `any`)
- Follow functional React components with hooks exclusively
- Prefer RTK thunks for async operations
- Always type React props inline within the component signature
- Run stylelint after any CSS file changes: `npm run stylelint`
- Never pass props that are available in global state

### Development Workflow

- **Development**: Do NOT run `npm run dev` - the user runs the app continuously in another terminal
- **Building**: Use `npm run build` to compile and verify if needed
- **Testing**: Use `npm run test` for quick tests or `npm run test:all` for comprehensive checks. This includes lint, tsc, build, and tests.
- For testing and exploration, use temporary Python scripts rather than modifying existing code

### Terminal Usage

- **Primary terminal**: GitBash is the standard shell
- **PowerShell**: Only use when explicitly required; open a separate PowerShell window

### React Component Patterns

```typescript
const MyComponent: React.FC<{
  propName: type;
  anotherProp: type;
}> = ({ propName, anotherProp }) => {
  // implementation
};
```

## Before You Start

1. **Understand the context**: Read relevant existing code and tests
2. **Ask clarifying questions** if requirements are ambiguous
3. **Plan your approach**: Use file structure and conventions as guides
4. **Implement incrementally**: Make small, verifiable changes

## During Implementation

1. **Check for existing patterns** in the codebase
2. **Write table-driven tests** using Vitest
3. **Update documentation** if adding new features
4. **Follow the established tech stack**: Node 22, Vite, React 19, TanStack Query
5. **Run verification after each significant change**

## Completion Checklist

Before declaring a task complete:

- [ ] Code follows project conventions and TypeScript strictness
- [ ] All CSS changes have been linted
- [ ] Tests are written for new functionality
- [ ] `npm run test:all` passes without errors
- [ ] No console warnings or errors
- [ ] Changes are minimal and focused on the task
- [ ] Documentation is updated if necessary

## Error Handling

If `npm run test:all` fails:

1. **Read the error output carefully** to understand what failed
2. **Fix the issue** in your code
3. **Re-run the command** to verify the fix
4. **Repeat until all checks pass**

If you're stuck or the error is unclear, use a subagent to investigate the problem.

## Communication

- Provide clear, concise responses explaining what was done
- Include file paths when referencing specific locations
- Report any blockers or decisions made during implementation
- Confirm task completion with verification output

## General Best Practices

- **Single responsibility**: Each function/component should have one clear purpose
- **DRY principle**: Reuse existing utilities and patterns
- **Performance**: Consider performance implications of large lists or complex renders
- **Accessibility**: Ensure components are keyboard accessible and screen reader friendly
- **Testing**: Aim for high test coverage, especially for critical paths
- **Documentation**: Keep README files and comments up to date
- **Git hygiene**: Make atomic commits with clear messages when applicable
