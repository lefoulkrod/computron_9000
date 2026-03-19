/* Browser Agent Test Suite - Shared JS */

// --- Score persistence via localStorage ---
var BT = {
  PAGES: [
    { id: "clicks_and_forms", name: "Clicks & Forms", href: "01_clicks_and_forms.html", total: 10 },
    { id: "navigation_and_scroll", name: "Navigation & Scroll", href: "02_navigation_and_scroll.html", total: 7 },
    { id: "keyboard_and_text", name: "Keyboard & Text", href: "03_keyboard_and_text.html", total: 7 },
    { id: "advanced", name: "Advanced Actions", href: "04_advanced.html", total: 7 },
    { id: "games", name: "Games & Puzzles", href: "05_games.html", total: 5 },
    { id: "captcha_and_drag", name: "Captcha & Image Drag", href: "06_captcha_and_drag.html", total: 5 }
  ],

  KEY: "browser_test_scores",

  getScores: function() {
    try { return JSON.parse(localStorage.getItem(this.KEY)) || {}; }
    catch(e) { return {}; }
  },

  savePageScore: function(pageId, passed, total) {
    var scores = this.getScores();
    scores[pageId] = { passed: passed, total: total, ts: Date.now() };
    localStorage.setItem(this.KEY, JSON.stringify(scores));
  },

  resetScores: function() {
    localStorage.removeItem(this.KEY);
  },

  getTotals: function() {
    var scores = this.getScores();
    var passed = 0;
    var total = 0;
    for (var i = 0; i < this.PAGES.length; i++) {
      var p = this.PAGES[i];
      total += p.total;
      if (scores[p.id]) passed += scores[p.id].passed;
    }
    return { passed: passed, total: total };
  }
};

// --- Task tracking for individual pages ---
function TaskTracker(pageId, totalTasks) {
  this.pageId = pageId;
  this.total = totalTasks;
  this.completed = {};
  this.logEl = document.getElementById("event-log");
}

TaskTracker.prototype.pass = function(n) {
  if (this.completed[n]) return;
  this.completed[n] = true;
  var li = document.querySelector('[data-task="' + n + '"]');
  if (li) {
    li.classList.add("pass");
    var s = li.querySelector(".status");
    if (s) { s.textContent = "PASS"; s.className = "status pass"; }
  }
  this._save();
  this._updateScore();
  this.log("Task " + n + " passed", "pass");
};

TaskTracker.prototype.count = function() {
  return Object.keys(this.completed).length;
};

TaskTracker.prototype.log = function(msg, cls) {
  if (!this.logEl) return;
  var d = document.createElement("div");
  d.className = "entry" + (cls ? " " + cls : "");
  d.textContent = "[" + new Date().toLocaleTimeString() + "] " + msg;
  this.logEl.insertBefore(d, this.logEl.firstChild);
};

TaskTracker.prototype._save = function() {
  BT.savePageScore(this.pageId, this.count(), this.total);
};

TaskTracker.prototype._updateScore = function() {
  var el = document.getElementById("page-score");
  if (el) el.textContent = this.count() + " / " + this.total;
  var bar = document.getElementById("progress-fill");
  if (bar) bar.style.width = (this.count() / this.total * 100) + "%";
};
