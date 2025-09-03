# MARIO GAME
create a mario brothers inspired side scoller game using javascript. you may also use CSS. the entrypoint should be an index.html file.
## Game Assets
YOU MUST create SVGs for all visual game assets
- player character should have blue overalls, a red had, and black shoes
- enemy character should be brown with white "googly" eyes and black shoes
- blocks should be gold with a question mark on them
- coin should be gold and round with a star or asterick style visual and should spin while falling
- the ground should be green
- the background should be blue (doesnt have to be SVG)
- there should be white clouds in the sky in fixed positions
do not use any audio game assets
## Acceptance Criteria
- the player should be able to move left, right, and jump
- blocks should be rendered in the air, above the players head
- enemies should move along the ground, similar to the player
- the player should be able to jump high enough to land on the blocks
- the players jumping movement should approximate actual physics
## Functional Requirements
- the player should get 3 lives. 
- the game can be restarted after 3 lives. 
- enemies should scroll in from right to left and should spawn randomly. 
- the player should be able to kill enemies by jumping on them. -
- killing an enemy earns 20 points. 
- players should be able to break blocks by jumping into it from below. 
- each block should be worth 10 points. 
- some blocks should spawn coins. collected coins are worth 100 points. 
- if a player lands on top of a block, the block should not break and they should remain on top.  
## Non Functional Requirements
- user should be able to run the game using a simple HTTP server from the project root (you do not need to install this as a dep)
- use easy to change constants for things like gravity, player speed, enemy speed, etc.
- use vite as the modern dev server and bundler. add an npm script dev that runs vite (dont run it yourself)

--------------------------
# Software Assignment: Mario-Inspired Python Game

## Functional Requirements

1. **Player Character**

   * Controlled with keyboard (left, right, jump).
   * 3 lives total; losing all lives restarts the game.

2. **Environment**

   * Blue background.
   * Blocks that the player can jump into and break.
   * Some blocks contain coins that are collected when broken.

3. **Enemies**

   * Enemies move horizontally on platforms.
   * Player can kill an enemy by jumping on top of it.

4. **Gameplay**

   * Coins increase the score.
   * Losing a life occurs when colliding with an enemy from the side or below.
   * Game restarts after all lives are lost.

## Technical Requirements

1. Must be implemented in **Python with Pygame**.
2. Must use **sprites** for player and enemy characters.

   * Sprites can be either:

     * Downloaded from the internet using `curl`
     * OR generated programmatically (e.g., simple shapes or generated images).
3. Assets (blocks, enemies, player, background) must be in formats appropriate for Pygame (e.g., PNG for images).
4. The game must run as a **single Python script** with no manual asset preparation required beyond what the script itself downloads or generates.

# Coding Assignment - Web browser based OS simulator
create a browser based OS simulator
- a desktop with a background color or gradient; settings to configure different backgrounds
- a taskbar with start menu and clock
- working sample applications; file explorer, web browser, terminal
- windows should be resizable by dragging the edges; should be able to maximize and minimize them; should be able to drag them around
- use only javascript, html, css, and svg
- generate SVGs for all icons
- should be able to run this from the workspace root by using npx vite or having installed vite and running it from a package.json script
- should simulate a shutdown procedure

{
  "artifacts": [
    {
      "acceptance_criteria": [
        "The page loads without external assets and displays an empty game area.",
        "Score and lives counters are visible and initially show 0 points and 3 lives."
      ],
      "depends_on": [],
      "detailed_requirements": [
        "Include a root <div id=\"game-root\"></div> where the SVG canvas will be injected.",
        "Link the stylesheet and main JavaScript module.",
        "Display a score and lives counter in the UI."
      ],
      "name": "HTML entry point",
      "path": "src/index.html",
      "user_stories": [
        "As a player I want a web page that loads the game so that I can start playing immediately."
      ]
    },
    {
      "acceptance_criteria": [
        "The game area occupies the defined width/height and UI text is readable.",
        "No scrollbars appear during gameplay."
      ],
      "depends_on": [],
      "detailed_requirements": [
        "Set the body margin to 0 and center the game area.",
        "Define fonts for UI text.",
        "Provide basic styling for the score/lives overlay."
      ],
      "name": "Global styles",
      "path": "src/styles.css",
      "user_stories": [
        "As a player I want the game canvas to have a consistent visual style so that the experience feels polished."
      ]
    },
    {
      "acceptance_criteria": [
        "Calling createPlayer() returns a valid SVG element representing the player.",
        "Blocks and coins render correctly when appended to the DOM."
      ],
      "depends_on": [],
      "detailed_requirements": [
        "Expose functions to create player, enemy, block, and coin SVG groups.",
        "All SVGs must be styled via inline attributes (no external images).",
        "Provide a method to clone assets for multiple instances."
      ],
      "name": "Asset Factory",
      "path": "src/assetFactory.js",
      "user_stories": [
        "As a developer I want a utility that creates reusable SVG elements so that graphics are generated programmatically."
      ]
    },
    {
      "acceptance_criteria": [
        "When ArrowLeft is held, left state is true; releasing sets it to false.",
        "Pressing ArrowUp triggers a single jump flag that resets after the game loop processes it."
      ],
      "depends_on": [],
      "detailed_requirements": [
        "Listen for ArrowLeft, ArrowRight, and ArrowUp key events.",
        "Expose a state object { left: boolean, right: boolean, jump: boolean }.",
        "Prevent default scrolling behavior when these keys are pressed."
      ],
      "name": "Input Handler",
      "path": "src/inputHandler.js",
      "user_stories": [
        "As a player I want to control the character with arrow keys so that I can move and jump."
      ]
    },
    {
      "acceptance_criteria": [
        "Player moves horizontally at a constant speed when left/right inputs are active.",
        "Jumping lifts the player to a peak height and then falls back under gravity.",
        "Lives start at 3 and decrement correctly on lethal collisions."
      ],
      "depends_on": [
        "Asset Factory",
        "Input Handler"
      ],
      "detailed_requirements": [
        "Instantiate the player SVG via Asset Factory.",
        "Update position based on input state each frame.",
        "Implement gravity and jump mechanics with a configurable jump height.",
        "Expose collision bounds for interaction with enemies, blocks, and coins.",
        "Track remaining lives and provide a method to decrement lives."
      ],
      "name": "Player Module",
      "path": "src/player.js",
      "user_stories": [
        "As a player I want my character to run left/right and jump so that I can navigate the level."
      ]
    },
    {
      "acceptance_criteria": [
        "Enemies spawn at x = game width and travel left until x < -enemy width, then are removed.",
        "When player collides from above, enemy is marked as defeated."
      ],
      "depends_on": [
        "Asset Factory"
      ],
      "detailed_requirements": [
        "Create enemy SVG via Asset Factory.",
        "Move left at a constant speed each frame.",
        "Provide a method to check if the player landed on top (collision from above).",
        "Self\u2011destruct when off\u2011screen or when defeated."
      ],
      "name": "Enemy Module",
      "path": "src/enemy.js",
      "user_stories": [
        "As a player I want enemies to appear from the right side randomly so that the game feels dynamic."
      ]
    },
    {
      "acceptance_criteria": [
        "Bottom collision triggers block removal and appropriate point award.",
        "Top collision does not remove the block and allows the player to stand.",
        "Blocks with coins award 100 points and display a brief coin pop\u2011up."
      ],
      "depends_on": [
        "Asset Factory"
      ],
      "detailed_requirements": [
        "Generate a block SVG; optionally embed a coin SVG inside.",
        "Detect upward collisions from the player.",
        "When hit from below, if it contains a coin, replace coin with a collected animation and award 100 points; otherwise award 10 points.",
        "If the player lands on top, block remains solid and the player can stand on it.",
        "After being hit, the block is removed from the game world."
      ],
      "name": "Block Module",
      "path": "src/block.js",
      "user_stories": [
        "As a player I want to break blocks by jumping into them from below so that I earn points.",
        "As a player I want some blocks to contain coins that give extra points when collected so that I am rewarded."
      ]
    },
    {
      "acceptance_criteria": [
        "Score increments correctly for enemy defeats (20), block breaks (10), and coin collection (100).",
        "Lives decrement only on lethal collisions and never drop below zero."
      ],
      "depends_on": [],
      "detailed_requirements": [
        "Maintain numeric counters for score and lives.",
        "Provide methods addPoints(points) and loseLife().",
        "Update the UI overlay in index.html whenever values change."
      ],
      "name": "Score & Lives Manager",
      "path": "src/scoreManager.js",
      "user_stories": [
        "As a player I want to see my current score and remaining lives so that I know my progress."
      ]
    },
    {
      "acceptance_criteria": [
        "The game begins with player, score, and lives displayed.",
        "Enemies and blocks appear as specified and interact correctly with the player.",
        "When lives reach zero, the engine resets all entities, score returns to 0, and lives return to 3.",
        "No memory leaks occur after multiple restarts (entities are properly disposed)."
      ],
      "depends_on": [
        "Player Module",
        "Enemy Module",
        "Block Module",
        "Score & Lives Manager",
        "Input Handler"
      ],
      "detailed_requirements": [
        "Initialize the game world, create the player, and start the main loop using requestAnimationFrame.",
        "Spawn enemies at random intervals (e.g., 1\u20133 seconds).",
        "Spawn blocks at predefined positions; randomly designate some as coin blocks.",
        "Handle collision detection between player, enemies, and blocks.",
        "Award points and manage lives via Score & Lives Manager.",
        "Detect game over (lives === 0) and reset the entire state to initial conditions.",
        "Expose a public start() method to begin or restart the game."
      ],
      "name": "Game Engine",
      "path": "src/gameEngine.js",
      "user_stories": [
        "As a player I want the game to start, run, and restart after I lose all lives so that I can keep playing."
      ]
    },
    {
      "acceptance_criteria": [
        "All tests pass with jest and coverage report shows full coverage of critical paths.",
        "Tests run in CI without requiring a browser."
      ],
      "depends_on": [
        "Game Engine",
        "Player Module",
        "Enemy Module",
        "Block Module",
        "Score & Lives Manager"
      ],
      "detailed_requirements": [
        "Write jest tests covering score updates, life loss, enemy defeat, block breaking, and game restart.",
        "Mock DOM interactions where necessary using jsdom.",
        "Ensure 100% branch coverage for the Game Engine module."
      ],
      "name": "Unit Tests",
      "path": "tests/gameEngine.test.js",
      "user_stories": [
        "As a developer I want automated tests for core game logic so that regressions are caught early."
      ]
    }
  ],
  "assumptions": [
    "The game runs in a modern browser supporting ES6 modules and requestAnimationFrame.",
    "All visual elements are generated as inline SVG via the svg.js library.",
    "Audio feedback (e.g., jump, coin) is optional and handled by howler if present.",
    "The game area has a fixed width and height (e.g., 800x400px).",
    "Keyboard input is limited to ArrowLeft, ArrowRight, ArrowUp for movement and jumping.",
    "Collision detection is axis\u2011aligned bounding box based.",
    "Game state (score, lives) is stored in memory; no persistence across page reloads.",
    "Testing focuses on pure JavaScript modules; DOM\u2011related rendering is mocked with jsdom."
  ],
  "dependency_manager": "npm",
  "language": "javascript",
  "packages": [
    "svg.js",
    "lodash",
    "howler"
  ],
  "success_criteria": [
    "Player can move left/right and jump using keyboard controls.",
    "Player starts with exactly three lives and loses one on enemy contact from the side or bottom.",
    "Game restarts automatically after the third life is lost.",
    "Enemies spawn at random intervals from the right, move left, and are removed when off\u2011screen.",
    "Jumping on an enemy destroys it and awards 20 points.",
    "Blocks break when hit from below, awarding 10 points; blocks containing coins award 100 points and display a coin SVG.",
    "Landing on top of a block does not break it and the player can stand on it.",
    "Score updates correctly for all actions and is displayed on screen.",
    "All modules have unit tests passing in the jest framework."
  ],
  "summary": "A Mario-inspired side\u2011scroll platformer built with HTML, CSS, and JavaScript using SVG for all visual assets. The player has 3 lives, can defeat enemies by jumping on them, break blocks, collect coins, and the game restarts after all lives are lost.",
  "test_framework": "jest"
}

[
  {
    "command": {
      "run": "npm init -y",
      "timeout_sec": 60
    },
    "id": "step-1",
    "step_kind": "command",
    "title": "Initialize JavaScript project environment"
  },
  {
    "file_path": "src/index.html",
    "id": "step-2",
    "implementation_details": [
      "Include a proper DOCTYPE and <html> structure with <head> and <body>.",
      "In <head>, set <meta charset=\"UTF-8\">, a descriptive <title>, and a <link rel=\"stylesheet\" href=\"styles.css\"> referencing the global stylesheet.",
      "Add a <script type=\"module\" src=\"main.js\"></script> (or appropriate main module) to load the game logic.",
      "Insert a root container <div id=\"game-root\"></div> where the SVG canvas will be injected by JavaScript.",
      "Add UI elements for score and lives counters, e.g., <div id=\"ui\"><span id=\"score\">Score: 0</span> <span id=\"lives\">Lives: 3</span></div>.",
      "Ensure no external assets (images, fonts) are referenced; only internal CSS/JS files.",
      "The page must load without errors and display an empty game area with visible counters."
    ],
    "step_kind": "file",
    "title": "Create HTML entry point"
  },
  {
    "file_path": "src/styles.css",
    "id": "step-3",
    "implementation_details": [
      "Reset body margin and padding to 0; set overflow hidden to prevent scrollbars during gameplay.",
      "Center the game area horizontally and vertically using flexbox or grid on the body.",
      "Define a fixed width and height for #game-root (e.g., 800px by 600px) and give it a background color.",
      "Set a default font-family and font-size for UI text, ensuring readability.",
      "Style the #ui container to position it as an overlay (e.g., absolute top-left) with appropriate spacing and contrast.",
      "Provide styling for #score and #lives spans (margin, color).",
      "Include any needed CSS variables for colors used by SVG assets (e.g., --player-color).",
      "Ensure the stylesheet does not introduce any external font imports."
    ],
    "step_kind": "file",
    "title": "Create global stylesheet"
  },
  {
    "file_path": "src/assetFactory.js",
    "id": "step-4",
    "implementation_details": [
      "Export functions: createPlayer(), createEnemy(), createBlock({ hasCoin: boolean }), createCoin(). Each returns an SVG <g> element ready to be appended to the game SVG.",
      "All SVG elements must be constructed using DOM methods (document.createElementNS) with the SVG namespace.",
      "Define the visual appearance of each asset using inline attributes only (e.g., <rect fill=\"#ff0\" stroke=\"#000\" ...>). No external image references.",
      "Player asset: simple rectangle or path representing a Mario\u2011like character; include a baseline for collision detection.",
      "Enemy asset: simple rectangle or path with distinct fill color; size comparable to player.",
      "Block asset: square with optional coin indicator; when hasCoin is true, embed a smaller circle or coin shape inside the block.",
      "Coin asset: small circle with golden fill and optional sparkle path; should be positioned relative to its parent block if generated via createBlock.",
      "Provide a utility function cloneAsset(svgElement) that returns a deep clone suitable for creating multiple instances without re\u2011creating the DOM structure each time.",
      "Each creation function must set a data attribute (e.g., data-type=\"player\") to aid collision detection later.",
      "All assets should have their origin (0,0) at the top\u2011left of the element to simplify positioning logic."
    ],
    "step_kind": "file",
    "title": "Implement Asset Factory module"
  },
  {
    "file_path": "src/inputHandler.js",
    "id": "step-5",
    "implementation_details": [
      "Export an object inputState with boolean properties: left, right, jump.",
      "Provide an initInputHandler() function that registers keydown and keyup listeners on the window object.",
      "On keydown:",
      "  - ArrowLeft sets inputState.left = true.",
      "  - ArrowRight sets inputState.right = true.",
      "  - ArrowUp sets inputState.jump = true **only if it was previously false** (to generate a single jump event per press).",
      "On keyup:",
      "  - ArrowLeft sets inputState.left = false.",
      "  - ArrowRight sets inputState.right = false.",
      "  - ArrowUp does **not** modify inputState.jump; the game loop is responsible for resetting jump to false after processing.",
      "Prevent the default browser scrolling behavior for the Arrow keys by calling event.preventDefault() within the listeners.",
      "Ensure listeners are attached only once; subsequent calls to initInputHandler should not duplicate handlers.",
      "Export a cleanupInputHandler() function that removes the registered listeners, to be used when the game is restarted or disposed."
    ],
    "step_kind": "file",
    "title": "Implement Input Handler module"
  }
]