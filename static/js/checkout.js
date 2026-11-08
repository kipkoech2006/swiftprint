/* Order form: live price, quantity buttons, multi-file picker (drag & drop), validation,
   and upload with a progress bar. Falls back to a normal form post if anything is unsupported. */
(function () {
  var form = document.getElementById('order-form');
  if (!form) return;

  var cfg = JSON.parse(document.getElementById('order-config').textContent);
  var input = document.getElementById('files');
  var zone = document.getElementById('dropzone');
  var list = document.getElementById('file-list');
  var errBox = document.getElementById('form-errors');
  var totalEl = document.getElementById('total');
  var qtyEl = document.getElementById('qty');
  var bar = document.getElementById('progress');
  var submitBtn = document.getElementById('send');
  var selected = [];
  var canRebuild = true;

  /* ---------- price ---------- */
  function total() {
    var unit = cfg.base;
    form.querySelectorAll('select[data-spec]').forEach(function (s) {
      var o = s.options[s.selectedIndex];
      if (o) unit += parseInt(o.getAttribute('data-add') || '0', 10);
    });
    var q = Math.max(1, parseInt(qtyEl.value, 10) || 1);
    return unit * q;
  }
  function refreshTotal() { if (totalEl) totalEl.textContent = 'KES ' + total().toLocaleString(); }
  form.querySelectorAll('select[data-spec]').forEach(function (s) { s.addEventListener('change', refreshTotal); });
  if (qtyEl) qtyEl.addEventListener('input', refreshTotal);
  form.querySelectorAll('[data-qty]').forEach(function (b) {
    b.addEventListener('click', function () {
      var v = Math.max(1, (parseInt(qtyEl.value, 10) || 1) + parseInt(b.getAttribute('data-qty'), 10));
      qtyEl.value = v; refreshTotal();
    });
  });
  refreshTotal();

  /* ---------- files ---------- */
  function size(n) { return n < 1048576 ? Math.max(1, Math.round(n / 1024)) + ' KB' : (n / 1048576).toFixed(1) + ' MB'; }
  function ext(name) { var i = name.lastIndexOf('.'); return i < 0 ? '' : name.slice(i + 1).toLowerCase(); }

  function render() {
    if (!list) return;
    list.innerHTML = '';
    selected.forEach(function (f, i) {
      var li = document.createElement('li');
      var nm = document.createElement('span'); nm.className = 'nm'; nm.textContent = f.name;
      var sz = document.createElement('span'); sz.className = 'sz'; sz.textContent = size(f.size);
      li.appendChild(nm); li.appendChild(sz);
      if (canRebuild) {
        var rm = document.createElement('button');
        rm.type = 'button'; rm.setAttribute('aria-label', 'Remove ' + f.name); rm.textContent = '×';
        rm.addEventListener('click', function () { selected.splice(i, 1); sync(); });
        li.appendChild(rm);
      }
      list.appendChild(li);
    });
  }

  function sync() {
    try {
      var dt = new DataTransfer();
      selected.forEach(function (f) { dt.items.add(f); });
      input.files = dt.files;
    } catch (e) { canRebuild = false; }
    render();
  }

  function addFiles(files) {
    var problems = [];
    if (!canRebuild) selected = [];
    Array.prototype.forEach.call(files, function (f) {
      if (cfg.allowed.indexOf(ext(f.name)) < 0) { problems.push('“' + f.name + '” is not a supported file type.'); return; }
      if (f.size > cfg.maxFileMb * 1048576) { problems.push('“' + f.name + '” is bigger than ' + cfg.maxFileMb + ' MB.'); return; }
      if (f.size === 0) { problems.push('“' + f.name + '” is empty.'); return; }
      if (selected.some(function (s) { return s.name === f.name && s.size === f.size; })) return;
      if (selected.length >= cfg.maxFiles) { problems.push('You can send up to ' + cfg.maxFiles + ' files.'); return; }
      selected.push(f);
    });
    sync();
    if (problems.length) showErrors(problems); else clearErrors();
  }

  if (input) {
    input.addEventListener('change', function () { addFiles(input.files); });
    if (zone) {
      ['dragenter', 'dragover'].forEach(function (t) {
        zone.addEventListener(t, function (e) { e.preventDefault(); zone.classList.add('over'); });
      });
      ['dragleave', 'drop'].forEach(function (t) {
        zone.addEventListener(t, function (e) { e.preventDefault(); zone.classList.remove('over'); });
      });
      zone.addEventListener('drop', function (e) { if (e.dataTransfer) addFiles(e.dataTransfer.files); });
    }
  }

  /* ---------- errors ---------- */
  function showErrors(list_) {
    errBox.innerHTML = '';
    var ul = document.createElement('ul');
    list_.forEach(function (m) { var li = document.createElement('li'); li.textContent = m; ul.appendChild(li); });
    errBox.appendChild(ul);
    errBox.hidden = false;
    if (errBox.scrollIntoView) errBox.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }
  function clearErrors() { errBox.hidden = true; errBox.innerHTML = ''; }

  function validate() {
    var errs = [];
    var nameEl = form.querySelector('[name=customer_name]');
    var phoneEl = form.querySelector('[name=whatsapp]');
    if (!nameEl || !nameEl.value.trim()) errs.push('Enter your name.');
    if (!phoneEl || !/^(?:\+?254|0)?[71]\d{8}$/.test(phoneEl.value.replace(/[\s-]/g, '')))
      errs.push('Enter a valid WhatsApp number, for example 0712 345 678.');
    if (cfg.filesRequired && !selected.length && !(input && input.files.length))
      errs.push('Please upload at least one file to print or edit.');
    return errs;
  }

  /* ---------- submit ---------- */
  form.addEventListener('submit', function (e) {
    var errs = validate();
    if (errs.length) { e.preventDefault(); showErrors(errs); return; }
    if (!window.XMLHttpRequest || !window.FormData) return;   // plain form post
    e.preventDefault();
    clearErrors();
    submitBtn.disabled = true;
    var label = submitBtn.textContent;
    submitBtn.textContent = 'Sending…';

    var xhr = new XMLHttpRequest();
    xhr.open('POST', form.action);
    xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
    xhr.setRequestHeader('Accept', 'application/json');
    xhr.upload.onprogress = function (ev) {
      if (ev.lengthComputable && bar) { bar.hidden = false; bar.value = Math.round(ev.loaded / ev.total * 100); }
    };
    function fail(msgs) {
      submitBtn.disabled = false; submitBtn.textContent = label;
      if (bar) bar.hidden = true;
      showErrors(msgs);
    }
    xhr.onload = function () {
      var data = null;
      try { data = JSON.parse(xhr.responseText); } catch (x) {}
      if (xhr.status === 200 && data && data.ok) { window.location.href = data.redirect; return; }
      fail(data && data.errors ? data.errors : ['Something went wrong. Please try again.']);
    };
    xhr.onerror = function () { fail(['Network problem. Check your connection and press Send again.']); };
    xhr.send(new FormData(form));
  });
})();
