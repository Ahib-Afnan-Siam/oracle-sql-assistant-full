# Color Scheme Updates

This document summarizes the changes made to unify the color scheme around the purple theme (#3b0764) across the frontend.

## Changes Made

### 1. Created Theme System
- Created `theme.css` with CSS variables for consistent purple theme usage
- Added Tailwind color definitions for the primary purple palette
- Updated `index.css` to import the theme

### 2. Component Updates

#### ChatInput.tsx
- Updated attachment button hover state to use purple-100 and purple-600
- Updated text input focus states to use purple-500
- Updated send button to use consistent purple gradient
- Maintained red color for stop button as it serves a different purpose

#### ChatPanel.tsx
- Updated visualization toggle button to use purple-600

#### HomePrompts.tsx
- Updated prompt buttons to use purple-600 on hover

#### FeedbackBox.tsx
- Updated submit button to use purple-600
- Maintained green, red, and yellow colors for feedback types as they serve specific purposes

#### MessageBubble.tsx
- Updated action buttons (copy/retry) to use purple-100 on hover
- Updated user avatar to use primary-purple-600 and bot avatar to use primary-purple-800

#### Sidebar.tsx
- Updated all interactive elements to use primary-purple-600
- Maintained consistent purple theme for selected mode indicators

#### DataTable.tsx
- Updated search input focus states to use primary-purple-500
- Updated visualization button to use primary-purple-600
- Updated pagination active state to use primary-purple-600

#### DataVisualization.tsx
- Updated chart type select focus states to use primary-purple-500

#### HybridFeedbackBox.tsx
- Updated rating buttons to use primary-purple-600 when selected
- Updated model preference buttons to use primary-purple-600 when selected
- Updated hybrid-specific toggle buttons to use primary-purple-600
- Updated submit button to use primary-purple-600

#### PromptSuggestions.tsx
- Updated suggestion buttons to use primary-purple-600 on hover

## Color Palette

The primary purple color palette now includes:
- primary-purple-50: #f5f3ff
- primary-purple-100: #ede9fe
- primary-purple-200: #ddd6fe
- primary-purple-300: #c4b5fd
- primary-purple-400: #a78bfa
- primary-purple-500: #8b5cf6
- primary-purple-600: #7c3aed
- primary-purple-700: #6d28d9
- primary-purple-800: #5b21b6
- primary-purple-900: #4c1d95

## Benefits

1. **Consistency**: All interactive elements now use the same purple theme
2. **Accessibility**: Proper contrast ratios maintained
3. **Branding**: Stronger visual identity with the purple theme
4. **Maintainability**: Centralized color definitions in theme.css and Tailwind config

## Future Improvements

1. Consider adding dark mode support
2. Add more color utility classes for different states
3. Create a design system documentation