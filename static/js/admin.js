/* Admin: instant thumbnails of photos you are about to upload. */
(function () {
  document.querySelectorAll('input[data-preview]').forEach(function (input) {
    var box = document.getElementById(input.getAttribute('data-preview'));
    if (!box) return;
    input.addEventListener('change', function () {
      box.innerHTML = '';
      Array.prototype.slice.call(input.files, 0, 40).forEach(function (f) {
        if (!/^image\//.test(f.type)) return;
        var img = document.createElement('img');
        img.alt = f.name;
        img.src = URL.createObjectURL(f);
        img.onload = function () { URL.revokeObjectURL(img.src); };
        box.appendChild(img);
      });
    });
  });
})();
