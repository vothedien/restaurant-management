export function LoginPage() {
  return (
    <section className="panel narrow">
      <h1>Login</h1>
      <p>Authentication is scaffolded; the login flow will be added in the auth module.</p>
      <form>
        <label>
          Username
          <input disabled placeholder="Coming soon" />
        </label>
        <label>
          Password
          <input disabled type="password" placeholder="Coming soon" />
        </label>
        <button disabled type="button">Sign in</button>
      </form>
    </section>
  );
}
