-- CreateTable
CREATE TABLE "bot_settings" (
    "id" INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT DEFAULT 1,
    "master_prompt" TEXT NOT NULL DEFAULT '',
    "guidelines" TEXT NOT NULL DEFAULT '',
    "exit_message" TEXT NOT NULL DEFAULT '',
    "automation_paused_global" BOOLEAN NOT NULL DEFAULT false
);

-- CreateTable
CREATE TABLE "subscribers" (
    "id" INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    "fanvue_user_uuid" TEXT NOT NULL,
    "handle" TEXT,
    "display_name" TEXT,
    "llm_context" TEXT NOT NULL DEFAULT '{}',
    "automation_enabled" BOOLEAN NOT NULL DEFAULT true,
    "messages_since_ppv_offer" INTEGER NOT NULL DEFAULT 0,
    "pending_ppv_message_uuid" TEXT,
    "exit_threshold" INTEGER,
    "created_at" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" DATETIME NOT NULL
);

-- CreateTable
CREATE TABLE "subscriber_facts" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "subscriber_id" INTEGER NOT NULL,
    "fact_key" TEXT NOT NULL,
    "fact_value" TEXT NOT NULL,
    "updated_at" DATETIME NOT NULL,
    CONSTRAINT "subscriber_facts_subscriber_id_fkey" FOREIGN KEY ("subscriber_id") REFERENCES "subscribers" ("id") ON DELETE CASCADE ON UPDATE CASCADE
);

-- CreateTable
CREATE TABLE "chat_messages" (
    "id" INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    "subscriber_id" INTEGER NOT NULL,
    "fanvue_message_uuid" TEXT NOT NULL,
    "direction" TEXT NOT NULL,
    "body" TEXT,
    "had_pricing" BOOLEAN NOT NULL DEFAULT false,
    "purchased_at_raw" TEXT,
    "sent_at" TEXT,
    "created_at" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "chat_messages_subscriber_id_fkey" FOREIGN KEY ("subscriber_id") REFERENCES "subscribers" ("id") ON DELETE CASCADE ON UPDATE CASCADE
);

-- CreateIndex
CREATE UNIQUE INDEX "subscribers_fanvue_user_uuid_key" ON "subscribers"("fanvue_user_uuid");

-- CreateIndex
CREATE UNIQUE INDEX "subscriber_facts_subscriber_id_fact_key_key" ON "subscriber_facts"("subscriber_id", "fact_key");

-- CreateIndex
CREATE UNIQUE INDEX "chat_messages_fanvue_message_uuid_key" ON "chat_messages"("fanvue_message_uuid");
