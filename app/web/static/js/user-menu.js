// User menu dropdown functionality

(() => {
  function initUserMenu() {
    document.addEventListener("DOMContentLoaded", function () {
      const userMenuButton = document.getElementById("user-menu-button");
      const userMenuDropdown = document.getElementById("user-menu-dropdown");

      if (userMenuButton && userMenuDropdown) {
        userMenuButton.addEventListener("click", function (e) {
          e.stopPropagation();
          userMenuDropdown.classList.toggle("hidden");
        });

        document.addEventListener("click", function (e) {
          if (
            !userMenuButton.contains(e.target) &&
            !userMenuDropdown.contains(e.target)
          ) {
            userMenuDropdown.classList.add("hidden");
          }
        });

        document.addEventListener("keydown", function (e) {
          if (e.key === "Escape") {
            userMenuDropdown.classList.add("hidden");
          }
        });
      }
    });
  }

  initUserMenu();
})();
