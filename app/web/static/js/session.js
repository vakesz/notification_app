(() => {
  function checkSession() {
    fetch("/api/session/validate", {
      method: "GET",
      credentials: "same-origin",
    })
      .then((response) => {
        if (response.status === 401) {
          // Session invalid, redirect to login
          console.log("Session expired, redirecting to login");
          window.location.href = "/login";
        } else if (!response.ok) {
          console.warn("Session validation failed:", response.statusText);
          // Could also redirect to login on other errors
          if (response.status >= 400) {
            console.log(
              "Server error during session validation, redirecting to login",
            );
            window.location.href = "/login";
          }
        } else {
          console.log("Session validation successful");
        }
      })
      .catch((error) => {
        console.error("Error checking session:", error);
        // On network errors, could also redirect to login
        console.log(
          "Network error during session validation, redirecting to login",
        );
        window.location.href = "/login";
      });
  }

  // Check session every 5 minutes if user is logged in
  // This will be triggered if the session.user block is present in the HTML
  // Initial check after 30 seconds
  setTimeout(checkSession, 30000);

  // Then check every 5 minutes
  setInterval(checkSession, 5 * 60 * 1000); // 5 minutes

  // Also check when page becomes visible
  document.addEventListener("visibilitychange", function () {
    if (!document.hidden) {
      checkSession();
    }
  });

  // Check on page load
  document.addEventListener("DOMContentLoaded", function () {
    setTimeout(checkSession, 2000); // Check 2 seconds after page load
  });
})();
