# FRONTEND DEVELOPMENT GUIDANCE

## Creating new project/page/element:

Generate a [new project/page/element] based on the provided [screenshot/mockup] to display this [mock data] following these rules:

### Architecture:

- Index.jsx should contain only high-level components
- High level components should be placed in an elements folder located at the same location as index.jsx
- Low-level component handles maximum 1 API call each. Call the API using @tanstack/react-query useQuery hook following the example. Each low level component file can contain both the LoadingSkeleton and the main Component inside if clauses. The main component should be generated first and the LoadingSkeleton later to match the component. LoadingSkeleton should use the Shacdn library.

```
function Example() {
  const { isPending, error, data } = useQuery({
    queryKey: ['repoData'],
    queryFn: () =>
      fetch('API_ENDPOINT').then((res) =>
        res.json(),
      ),
  })

  if (isPending) return <LoadingSkeleton />

  if (error) return 'An error has occurred: ' + error.message

  return (
    <div>Component…</div>
  )
}
```

### Submodule folder structure:

```
[submodule]/
├── index.jsx # Entry point: only imports and high-level components
├── elements/ # Low-level UI building blocks
│ ├── Button.jsx
│ ├── Card.jsx
│ └── InputField.jsx
```

### Backend integration:

- Each component should only handle one API call, if multiple API calls are needed, separate the component into smaller components
- For API calls, use the library @tanstack/react-query, only one QueryClientProvider wrapper inside index.jsx, each child component inherits this query provider.

### Functional requirements:

- Every new component/page must be responsive, catering to both mobile and laptop users.
- Make sure that the user interface is intuitive to use, following design conventions.
- When possible, add interactivity to enhance user experience.

### Libraries & Assets:

- For charts, use Shadcn
- For state management, use Zustand as much as possible
- For more complex state management, use Redux
- Try to reuse components inside @/components if possible
- Avoid changing code outside of the current directory

### Formatting:

Format the code according to Prettier default formatting

```
{
  "arrowParens": "always",
  "bracketSpacing": true,
  "endOfLine": "lf",
  "htmlWhitespaceSensitivity": "css",
  "insertPragma": false,
  "singleAttributePerLine": false,
  "bracketSameLine": false,
  "jsxBracketSameLine": false,
  "jsxSingleQuote": false,
  "printWidth": 80,
  "proseWrap": "preserve",
  "quoteProps": "as-needed",
  "requirePragma": false,
  "semi": true,
  "singleQuote": false,
  "tabWidth": 2,
  "trailingComma": "es5",
  "useTabs": false,
  "embeddedLanguageFormatting": "auto",
  "vueIndentScriptAndStyle": false,
  "experimentalTernaries": false
}
```

## Debugging:

- Change the existing code as little as possible
- For any new elements needed, follow above instructions for new page/elements
