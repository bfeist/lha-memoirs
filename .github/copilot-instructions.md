# .github/copilot-instructions.md

Project overview: TypeScript.
Tech stack: Node 22, Vite, React 19, TanStack Query.
Conventions:

- Use strict TypeScript (no `any`), `skipLibCheck=false`.
- use temp python scripts whenever you're trying to run code for testing or exploration. you don't have to run code but when you do, use a temp script.
- Use functional React components with hooks.
- Prefer RTK thunks for async.
- Tests: Vitest; write table-driven tests.
  Build & run:
- Dev: `npm run dev`
- Build: `npm run build`
- Test: `npm run test`
- Test all including lint and tsc: `npm run test:all`

I'm using gitbash all the time for every terminal that you control. If you need to run a powershell command, open a powershell window.

When writing on the react side, don't do "npm run dev". I'm usually already running the app. You can do npm run build if you just want to see if the code compiles but you don't have to.

Always run a stylelint check whenever you change a css file.

When making React components, never pass as props something that is available in global state.

When dealing with React props, always type the props inline rather than using an external type or interface. Such as:
const YearCanvas: React.FC<{
year: number;
}> = ({ year }) => {}
