# Scenario 04: Browser Form Filling with Validation Errors

## Purpose

Tests that form state survives compaction: which fields have been filled, which failed validation, what the current validation errors are, and what the agent was about to fix. Forms are stateful — unlike research tasks where only results matter, the agent needs to know the process (which fields are done, which need retry).

## Agent Type

BROWSER_AGENT

## Conversation

Agent fills out a job application form. Encounters validation errors on first submit (email format, missing required field, resume file too large). Fixes some errors, still has work remaining when compaction triggers.

```
system: You are a helpful AI assistant with browser tools.

user: Fill out the job application at https://careers.example.com/apply/senior-engineer-4521. Use my info: name is Sarah Chen, email sarah.chen@gmail.com, phone 512-555-0147, 8 years experience. I have a resume at /home/computron/sarah_resume.pdf.

A: I'll navigate to the application page.
  [Called tools: browse_page]

tool (browse_page): [Page: Apply - Senior Software Engineer | https://careers.example.com/apply/senior-engineer-4521 | 200]
  [Viewport: 0-900 of 4000px]
  [h1] Senior Software Engineer — Application
  [h2] Personal Information
  [1] [textbox] First Name *
  [2] [textbox] Last Name *
  [3] [textbox] Email Address *
  [4] [textbox] Phone Number
  [5] [combobox] Country * = "Select country"
  [h2] Professional Details
  [6] [textbox] Years of Experience *
  [7] [combobox] Current Role Level = "Select level"
  [8] [textarea] Cover Letter
  [9] [file input] Upload Resume * (PDF, max 5MB)
  [10] [checkbox] I agree to the privacy policy *
  [11] [button] Submit Application

A: I'll start filling in the personal information.
  [Called tools: fill_field]

tool (fill_field): [Page: Apply - Senior Software Engineer | https://careers.example.com/apply/senior-engineer-4521 | 200]
  [1] [textbox] First Name * = "Sarah"

A: [Called tools: fill_field]

tool (fill_field): [2] [textbox] Last Name * = "Chen"

A: [Called tools: fill_field]

tool (fill_field): [3] [textbox] Email Address * = "sarah.chen@gmail.com"

A: [Called tools: fill_field]

tool (fill_field): [4] [textbox] Phone Number = "512-555-0147"

A: [Called tools: select_option]

tool (select_option): [5] [combobox] Country * = "United States"

A: Now the professional details.
  [Called tools: fill_field]

tool (fill_field): [6] [textbox] Years of Experience * = "8"

A: [Called tools: select_option]

tool (select_option): [7] [combobox] Current Role Level = "Senior"

A: [Called tools: fill_field]

tool (fill_field): [8] [textarea] Cover Letter = "I am writing to express my interest in the Senior Software Engineer position. With 8 years of experience in full-stack development, I bring strong expertise in Python, React, and cloud infrastructure. I am particularly drawn to your team's work on distributed systems."

A: Now I'll upload the resume.
  [Called tools: click]

tool (click): [Page: Apply - Senior Software Engineer | https://careers.example.com/apply/senior-engineer-4521 | 200]
  [9] [file input] Upload Resume * — File selected: sarah_resume.pdf (8.2 MB)
  [Warning] File size exceeds maximum of 5MB

A: The resume file is too large (8.2 MB, max is 5 MB). Let me try to compress it first.
  [Called tools: run_bash_cmd]

tool (run_bash_cmd): gs -sDEVICE=pdfwrite -dCompatibilityLevel=1.4 -dPDFSETTINGS=/ebook -dNOPAUSE -dBATCH -sOutputFile=/home/computron/sarah_resume_compressed.pdf /home/computron/sarah_resume.pdf
  Output: Processing pages 1 through 3.
  Original: 8.2 MB → Compressed: 3.1 MB

A: Compressed to 3.1 MB. Let me upload the compressed version.
  [Called tools: browse_page]

tool (browse_page): [Page: Apply - Senior Software Engineer | https://careers.example.com/apply/senior-engineer-4521 | 200]
  [Viewport: 0-900 of 4000px]
  [h2] Personal Information
  [1] [textbox] First Name * = "Sarah"
  [2] [textbox] Last Name * = "Chen"
  [3] [textbox] Email Address * = "sarah.chen@gmail.com"
  [4] [textbox] Phone Number = "512-555-0147"
  [5] [combobox] Country * = "United States"
  [h2] Professional Details
  [6] [textbox] Years of Experience * = "8"
  [7] [combobox] Current Role Level = "Senior"
  [8] [textarea] Cover Letter = "I am writing to express my interest..."
  [9] [file input] Upload Resume * — No file selected
  [10] [checkbox] I agree to the privacy policy *
  [11] [button] Submit Application

A: The page refreshed and lost the file selection. Let me re-upload with the compressed file. But first let me check — the form fields are still filled in.
  [Called tools: click]

tool (click): [9] [file input] = sarah_resume_compressed.pdf (3.1 MB) ✓

A: Now I need to check the privacy checkbox and submit.
  [Called tools: click]

tool (click): [10] [checkbox] I agree to the privacy policy * = checked ✓

A: [Called tools: click]

tool (click): [Page: Apply - Senior Software Engineer | https://careers.example.com/apply/senior-engineer-4521 | 200]
  [Viewport: 0-900 of 4500px]
  [h1] Senior Software Engineer — Application
  [Error banner] Please fix the following errors:
  - Email: Please enter a valid company or professional email address. Free email providers (gmail, yahoo, hotmail) are not accepted.
  - LinkedIn Profile: This field is required.
  [h2] Personal Information
  [1] [textbox] First Name * = "Sarah"
  [2] [textbox] Last Name * = "Chen"
  [3] [textbox] Email Address * = "sarah.chen@gmail.com" [ERROR: invalid]
  [4] [textbox] Phone Number = "512-555-0147"
  [5] [combobox] Country * = "United States"
  [12] [textbox] LinkedIn Profile URL * [ERROR: required]
  [h2] Professional Details
  [6] [textbox] Years of Experience * = "8"
  [7] [combobox] Current Role Level = "Senior"
  [8] [textarea] Cover Letter = "I am writing to express my interest..."
  [9] [file input] Upload Resume * = sarah_resume_compressed.pdf (3.1 MB) ✓
  [10] [checkbox] I agree to the privacy policy * = checked ✓
  [11] [button] Submit Application

A: Two validation errors:
  1. **Email**: The form doesn't accept Gmail — it requires a company/professional email
  2. **LinkedIn Profile**: This field wasn't visible before (it appeared after selecting country). It's required.

  I don't have a professional email for Sarah, and I need her LinkedIn URL. Let me report this to the user.

  The application form is mostly filled out. Here's the current status:

  **Completed fields:**
  - First Name: Sarah ✓
  - Last Name: Chen ✓
  - Phone: 512-555-0147 ✓
  - Country: United States ✓
  - Years of Experience: 8 ✓
  - Current Role Level: Senior ✓
  - Cover Letter: Filled ✓
  - Resume: sarah_resume_compressed.pdf (3.1 MB) ✓
  - Privacy Policy: Agreed ✓

  **Errors to fix:**
  - Email: "sarah.chen@gmail.com" rejected — needs a professional/company email
  - LinkedIn Profile URL: Required field, I don't have this information

  Can you provide a professional email address and your LinkedIn URL?

user: Use sarah@chendev.io for email. LinkedIn is https://linkedin.com/in/sarachen-dev
```

## Compaction Boundary Analysis

With `keep_recent=6`:
- **Total messages**: 1 system + ~24 non-system
- **Pinned**: First user message (with Sarah's info, resume path, job URL)
- **Compacted**: Messages 2 through ~18 (initial form fill, file compression, re-upload, submit attempt, validation errors)
- **Kept**: Last 6 non-system messages (likely the error report, user's response with new email/LinkedIn)

### What crosses the compaction boundary

The user provided new email and LinkedIn. The agent needs to know:
- Which fields are already filled (don't re-enter them)
- Which fields have errors (email, LinkedIn)
- That the resume was compressed from 8.2MB to 3.1MB (don't re-upload the original)
- The compressed file path (`/home/computron/sarah_resume_compressed.pdf`)
- That the LinkedIn field wasn't visible initially (dynamic form)
- The exact form URL

Without the summary, the agent might re-fill all fields from scratch or try to upload the original too-large resume.

## Required Facts

| Fact | Anchored pattern |
|------|-----------------|
| Job URL | `r"careers\.example\.com/apply/senior-engineer-4521"` |
| First Name filled: Sarah | `r"[Ff]irst\s*[Nn]ame.*Sarah|Sarah.*filled|Sarah.*✓|Sarah\s+Chen|Sarah.*complet"` |
| Last Name filled: Chen | `r"[Ll]ast\s*[Nn]ame.*Chen|Chen.*filled|Chen.*✓|Sarah\s+Chen"` |
| Phone filled | `r"512.555.0147"` |
| Country: United States | `r"[Uu]nited\s+[Ss]tates|US[A]?"` |
| Years of Experience: 8 | `r"8\s*years?|[Ee]xperience.*8"` |
| Role Level: Senior | `r"[Ss]enior"` |
| Cover letter filled | `r"[Cc]over\s*[Ll]etter.*filled|[Cc]over\s*[Ll]etter.*✓|[Cc]over\s*[Ll]etter.*writ|[Cc]over\s*[Ll]etter.*complet|[Cc]over\s*[Ll]etter.*done"` |
| Resume compressed to 3.1MB | `r"3\.1\s*MB|compress"` |
| Compressed file path | `r"sarah_resume_compressed"` |
| Original too large (8.2MB, max 5MB) | `r"8\.2|too\s*large|exceed|over.?size|max.*5\s*MB"` |
| Email validation error — no Gmail | `r"[Gg]mail.*reject|[Gg]mail.*not\s*accept|professional\s*email|company\s*email|[Gg]mail.*invalid|[Gg]mail.*error|free\s*email.*not"` |
| LinkedIn field required | `r"[Ll]inked[Ii]n.*required|[Ll]inked[Ii]n.*missing|[Ll]inked[Ii]n.*need|[Ll]inked[Ii]n.*error"` |
| Privacy checkbox checked | `r"[Pp]rivacy.*check|[Pp]rivacy.*agree|[Pp]rivacy.*✓|[Pp]rivacy.*done|[Pp]rivacy.*accept"` |


## Probes

| Question | Pass pattern | Fail pattern |
|----------|-------------|-------------|
| What fields still need to be fixed on the application form? | `r"email|LinkedIn"` | `r"fix.*(first name|phone|country)|enter.*(first name|phone)"` |
| Why was the original email rejected? | `r"[Gg]mail|professional|company"` | — |
| What happened with the resume upload? | `r"compress|3\.1|too large|8\.2"` | — |
