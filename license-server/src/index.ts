import { handle, type CoreEnv } from "./core";
import { D1Db } from "./db";

type Env = CoreEnv & { DB: D1Database };

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    try {
      return await handle(req, env, new D1Db(env.DB));
    } catch {
      return new Response(JSON.stringify({ error: "server" }), { status: 500, headers: { "content-type": "application/json" } });
    }
  },
};
