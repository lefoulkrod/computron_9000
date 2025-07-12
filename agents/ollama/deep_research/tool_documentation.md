# Web Research Tools Documentation

This document provides detailed documentation for the web research tools used by the Deep Research Agent.

## Tool Overview

| Tool | Purpose | Key Features |
|------|---------|--------------|
| `search_google` | Find relevant web pages for a topic | Results include title, URL, and snippet |
| `get_webpage` | Extract full text content from a URL | Removes HTML, preserves text, extracts links |
| `get_webpage_summary` | Generate concise summary of a webpage | Handles large pages via section summaries |
| `get_webpage_summary_sections` | Get sectional summaries with position data | Useful for navigating long documents |
| `get_webpage_substring` | Extract specific portions of a webpage | Allows targeting specific content sections |
| `html_find_elements` | Extract specific HTML elements | Find elements by tag and content |

## Detailed Tool Documentation

### search_google

```python
async def search_google(query: str, max_results: int = 5) -> GoogleSearchResults:
```

#### Description
Performs a Google search and returns structured results.

#### Example Usage
```python
results = await search_google("climate change impacts on agriculture")
for result in results.results:
    print(f"Title: {result.title}")
    print(f"URL: {result.link}")
    print(f"Snippet: {result.snippet}")
    print("---")
```

#### Research Usage Guidelines
- Use specific queries rather than broad ones
- Include key terms for precision
- Use quotes for exact matches when necessary
- Try domain-specific terms for academic research
- Limit results to manageable numbers (3-5) for initial exploration

---

### get_webpage

```python
async def get_webpage(url: str) -> ReducedWebpage:
```

#### Description
Downloads a webpage, strips HTML tags, and returns the cleaned text content along with extracted links.

#### Example Usage
```python
webpage = await get_webpage("https://example.com/article")
print(f"Page content length: {len(webpage.page_text)}")
print(f"Number of links: {len(webpage.links)}")
```

#### Research Usage Guidelines
- Use for accessing full content when detail is important
- Check returned links for potential citation trails
- Be aware of potential large content returns
- Consider using summary methods for initial scanning

---

### get_webpage_summary

```python
async def get_webpage_summary(url: str) -> str:
```

#### Description
Downloads a webpage and generates a concise summary of its content.

#### Example Usage
```python
summary = await get_webpage_summary("https://example.com/long-article")
print(f"Summary: {summary}")
```

#### Research Usage Guidelines
- Use for quick understanding of a page's content
- Good for preliminary source assessment
- Helps decide if full content review is needed
- Use on multiple sources to compare information efficiently

---

### get_webpage_summary_sections

```python
async def get_webpage_summary_sections(url: str) -> List[SectionSummary]:
```

#### Description
Downloads a webpage and summarizes its content in sections, preserving structure.

#### Example Usage
```python
sections = await get_webpage_summary_sections("https://example.com/research-paper")
for i, section in enumerate(sections):
    print(f"Section {i+1}: {section.summary[:100]}...")
```

#### Research Usage Guidelines
- Useful for navigating structured long-form content
- Helps identify relevant sections for deeper reading
- Preserves document structure in summarization
- Use position data to retrieve full text of interesting sections

---

### get_webpage_substring

```python
async def get_webpage_substring(url: str, start: int, end: int) -> str:
```

#### Description
Fetches a webpage and returns a substring from the specified character positions.

#### Example Usage
```python
# Get text from positions identified in section summaries
sections = await get_webpage_summary_sections("https://example.com/article")
interesting_section = sections[2]
full_section_text = await get_webpage_substring(
    "https://example.com/article",
    interesting_section.starting_char_position,
    interesting_section.ending_char_position
)
```

#### Research Usage Guidelines
- Use with `get_webpage_summary_sections` to retrieve full text of interesting sections
- Useful for targeted information extraction
- Enables focused analysis of specific content areas
- Helps manage token usage by retrieving only needed content

---

### html_find_elements

```python
async def html_find_elements(html: str, tag: str, text: Optional[str] = None) -> List[HtmlElementResult]:
```

#### Description
Finds HTML elements with the specified tag and optional text content.

#### Example Usage
```python
# Get raw HTML first
raw_result = await _get_webpage_raw("https://example.com")
# Find all table elements
tables = await html_find_elements(raw_result.html, "table")
# Find paragraphs containing "climate change"
climate_paragraphs = await html_find_elements(raw_result.html, "p", "climate change")
```

#### Research Usage Guidelines
- Use for extracting structured data like tables
- Target specific information types (headings, lists, etc.)
- Extract citation elements from academic papers
- Useful for finding specific content within a page

## Tool Integration Patterns

### Basic Research Flow

1. **Search → Scan → Select → Analyze**
   ```python
   # Search for sources
   search_results = await search_google("topic of interest")
   
   # Scan summaries to identify promising sources
   for result in search_results.results[:3]:  # Focus on top 3
       summary = await get_webpage_summary(result.link)
       # Evaluate summary relevance
   
   # Select and get detailed content from best source
   full_content = await get_webpage(best_source_url)
   
   # Analyze specific elements if needed
   ```

### Deep Content Analysis

1. **Section Analysis for Long Documents**
   ```python
   # Get section summaries
   sections = await get_webpage_summary_sections(url)
   
   # Identify relevant sections
   relevant_sections = [s for s in sections if "keyword" in s.summary]
   
   # Get full text of relevant sections
   for section in relevant_sections:
       full_section = await get_webpage_substring(
           url, section.starting_char_position, section.ending_char_position
       )
       # Analyze full section content
   ```

## Source Citation Best Practices

When using these tools for research, proper citation is essential:

1. **Record all sources accessed**
   - Track URLs, titles, and access times
   - Note which tool was used to access each source

2. **Extract source metadata when possible**
   - Author information
   - Publication date
   - Publisher/organization

3. **Format citations appropriately**
   - Use the Source Tracker's citation formatting capabilities
   - Include access date for web sources
   - Specify which sections of content were used

4. **Cross-reference information**
   - Verify facts across multiple sources
   - Note discrepancies between sources
   - Assign higher confidence to consensus information
