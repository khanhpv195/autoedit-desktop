# bundle.social API — trích các endpoint dùng ở M4

Nguồn: https://api.bundle.social/swagger-json (tải 2026-11-20). Auth: header `x-api-key`. Base `https://api.bundle.social`.

## GET /api/v1/organization/ — Get organization

Retrieve your organization's details and plan. The `teams` field is deprecated and will be removed on 2026-11-15: to discover team IDs, use the paginated GET /api/v1/team.


Response 200:
```json
{
 "id": "string",
 "createdById": "string",
 "promotionCodeId?": "string",
 "name?": "string",
 "avatarUrl?": "string",
 "ref?": "string",
 "dailyPostLimit?": {
  "TWITTER?": "number",
  "FACEBOOK?": "number",
  "INSTAGRAM?": "number",
  "LINKEDIN?": "number",
  "YOUTUBE?": "number",
  "TIKTOK?": "number",
  "THREADS?": "number",
  "PINTEREST?": "number",
  "REDDIT?": "number",
  "DISCORD?": "number",
  "SLACK?": "number",
  "MASTODON?": "number",
  "BLUESKY?": "number",
  "GOOGLE_BUSINESS?": "number",
  "SNAPCHAT?": "number"
 },
 "dailyCommentLimit?": {
  "TWITTER?": "number",
  "FACEBOOK?": "number",
  "INSTAGRAM?": "number",
  "LINKEDIN?": "number",
  "YOUTUBE?": "number",
  "TIKTOK?": "number",
  "THREADS?": "number",
  "PINTEREST?": "number",
  "REDDIT?": "number",
  "DISCORD?": "number",
  "SLACK?": "number",
  "MASTODON?": "number",
  "BLUESKY?": "number",
  "GOOGLE_BUSINESS?": "number",
  "SNAPCHAT?": "number"
 },
 "monthlyImportLimitPerAccount?": "number",
 "commentImportLimitPerPost?": "number",
 "monthlyReviewImportLimitPerAccount?": "number",
 "monthlyMessageLimitPerAccount?": "number",
 "monthlyAutomationExecutionLimitPerAccount?": "number",
 "apiAccess": "boolean",
 "analyticsDisabled": "boolean",
 "analyticsPostsDisabled": "boolean",
 "uploadsCompressionEnabled": "boolean",
 "analyticsInterval?": "number",
 "analyticsPostsInterval?": "number",
 "forcedAccountAnalyticsDailyLimit?": "number",
 "forcedPostAnalyticsDailyLimit?": "number",
 "showVerboseErrors": "boolean",
 "disconnectCheckEnabled": "boolean",
 "deleteAccountAfter": "integer",
 "createdAt": "string",
 "updatedAt": "string",
 "deletedAt?": "string",
 "suspended?": "boolean",
 "createdBy": {
  "id": "string",
  "externalId": "string",
  "email": "string",
  "emailVerified?": "string",
  "firstName?": "string",
  "lastName?": "string",
  "avatarUrl?": "string",
  "timezone?": "string",
  "role": "enum:ADMIN|CUSTOMER",
  "createdAt": "string",
  "updatedAt": "string",
  "deletedAt?": "string"
 },
 "subscription?": {
  "id": "string",
  "organizationId": "string",
  "couponId?": "string",
  "promotionCodeId?": "string",
  "stripeSubscriptionId": "string",
  "stripeSubscriptionItems?": [
   {
    "id": "string",
    "price": "string",
    "quantity": "number"
   }
  ],
  "status": "enum:trialing|active|canceled|incomplete|incomplete_expired|past_due|unpaid|paused",
  "metadata?": {},
  "stripePriceId": "string",
  "tier": "enum:PRO|BUSINESS",
  "billingInterval": "enum:MONTHLY|YEARLY",
  "isCustomPrice": "boolean",
  "customPriceLabel?": "string",
  "customUnitAmount?": "integer",
  "customCurrency?": "string",
  "cancelAtPeriodEnd": "boolean",
  "created": "string",
  "currentPeriodStart": "string",
  "currentPeriodEnd": "string",
  "endedAt?": "string",
  "cancelAt?": "string",
  "canceledAt?": "string",
  "trialStart?": "string",
  "trialEnd?": "string",
  "maxMonthlyPosts?": "number",
  "maxMonthlyComments?": "number",
  "maxMonthlyUploads?": "number",
  "maxMonthlyImportedPosts?": "number",
  "pendingTier?": "enum:PRO|BUSINESS",
  "pendingBillingInterval?": "enum:MONTHLY|YEARLY",
  "pendingPriceId?": "string",
  "pendingEffectiveAt?": "string",
  "pendingScheduleId?": "string",
  "discountStart?": "string",
  "discountEnd?": "string",
  "createdAt": "string",
  "updatedAt": "string",
  "coupon?": {
   "id": "string",
   "name?": "string",
   "amountOff?": "number",
   "percentOff?": "number",
   "duration": "enum:forever|once|repeating",
   "durationInMonths?": "number",
   "maxRedemptions?": "number",
   "valid": "boolean",
   "createdAt": "string",
   "updatedAt": "string"
  },
  "promotionCode?": {
   "code": "string",
   "coupon": {
    "percentOff": "number",
    "duration": "enum:forever|once|repeating",
    "durationInMonths?": "number",
    "valid": "boolean"
   }
  }
 },
 "promotionCode?": {
  "code": "string",
  "coupon": {
   "percentOff": "number",
   "duration": "enum:forever|once|repeating",
   "durationInMonths?": "number",
   "valid": "boolean"
  }
 },
 "teams": [
  {
   "id": "string",
   "name": "string",
   "avatarUrl?": "string",
   "organizationId": "string",
   "createdById": "string",
   "createdAt": "string",
   "updatedAt": "string",
   "deletedAt?": "string"
  }
 ]
}
```


## GET /api/v1/organization/usage/posts — Get organization posts usage

See how many posts your organization has consumed against its plan limit for the current billing period. Use it to monitor quota before scheduling large batches.


Response 200:
```json
{
 "used": "number",
 "limit": "number",
 "remaining": "number"
}
```


## GET /api/v1/organization/usage/uploads — Get organization uploads usage

See how much upload capacity your organization has consumed against its plan limit for the current billing period.


Response 200:
```json
{
 "used": "number",
 "limit": "number",
 "remaining": "number"
}
```


## GET /api/v1/team/ — Get list of teams

List the teams in your organization with pagination. Use this to discover team IDs, which are required by most publishing and analytics endpoints.

- param query offset?: "integer"
- param query limit?: "integer"
- param query search?: "string"

Response 200:
```json
{
 "items": [
  {
   "id": "string",
   "name": "string",
   "avatarUrl?": "string",
   "organizationId": "string",
   "createdById": "string",
   "createdAt": "string",
   "updatedAt": "string",
   "deletedAt?": "string",
   "organization": {
    "id": "string",
    "createdById": "string",
    "promotionCodeId?": "string",
    "name?": "string",
    "avatarUrl?": "string",
    "ref?": "string",
    "dailyPostLimit?": {
     "TWITTER?": "number",
     "FACEBOOK?": "number",
     "INSTAGRAM?": "number",
     "LINKEDIN?": "number",
     "YOUTUBE?": "number",
     "TIKTOK?": "number",
     "THREADS?": "number",
     "PINTEREST?": "number",
     "REDDIT?": "number",
     "DISCORD?": "number",
     "SLACK?": "number",
     "MASTODON?": "number",
     "BLUESKY?": "number",
     "GOOGLE_BUSINESS?": "number",
     "SNAPCHAT?": "number"
    },
    "dailyCommentLimit?": {
     "TWITTER?": "number",
     "FACEBOOK?": "number",
     "INSTAGRAM?": "number",
     "LINKEDIN?": "number",
     "YOUTUBE?": "number",
     "TIKTOK?": "number",
     "THREADS?": "number",
     "PINTEREST?": "number",
     "REDDIT?": "number",
     "DISCORD?": "number",
     "SLACK?": "number",
     "MASTODON?": "number",
     "BLUESKY?": "number",
     "GOOGLE_BUSINESS?": "number",
     "SNAPCHAT?": "number"
    },
    "monthlyImportLimitPerAccount?": "number",
    "commentImportLimitPerPost?": "number",
    "monthlyReviewImportLimitPerAccount?": "number",
    "monthlyMessageLimitPerAccount?": "number",
    "monthlyAutomationExecutionLimitPerAccount?": "number",
    "apiAccess": "boolean",
    "analyticsDisabled": "boolean",
    "analyticsPostsDisabled": "boolean",
    "uploadsCompressionEnabled": "boolean",
    "analyticsInterval?": "number",
    "analyticsPostsInterval?": "number",
    "forcedAccountAnalyticsDailyLimit?": "number",
    "forcedPostAnalyticsDailyLimit?": "number",
    "showVerboseErrors": "boolean",
    "disconnectCheckEnabled": "boolean",
    "deleteAccountAfter": "integer",
    "createdAt": "string",
    "updatedAt": "string",
    "deletedAt?": "string",
    "suspended?": "boolean"
   },
   "createdBy": {
    "id": "string",
    "externalId": "string",
    "email": "string",
    "emailVerified?": "string",
    "firstName?": "string",
    "lastName?": "string",
    "avatarUrl?": "string",
    "timezone?": "string",
    "role": "enum:ADMIN|CUSTOMER",
    "createdAt": "string",
    "updatedAt": "string",
    "deletedAt?": "string"
   },
   "bots": [
    {
     "id": "string",
     "name": "string",
     "avatarUrl?": "string",
     "teamId": "string",
     "createdAt": "string",
     "updatedAt": "string",
     "deletedAt?": "string"
    }
   ],
   "socialAccounts": [
    {
     "id": "string",
     "type": "enum:TIKTOK|YOUTUBE|INSTAGRAM|FACEBOOK|TWITTER|THREADS|LINKEDIN|PINTEREST|REDDIT|MASTODON|DISCORD|SLACK|BLUESKY|GOOGLE_BUSINESS|SNAPCHAT",
     "teamId": "string",
     "username?": "string",
     "displayName?": "string",
     "bio?": "string",
     "avatarUrl?": "string",
     "externalId?": "string",
     "providerPageId?": "string",
     "userUsername?": "string",
     "userDisplayName?": "string",
     "userEmail?": "string",
     "userId?": "string",
     "channels?": [
      {
       "id": "string",
       "name?": "string",
       "username?": "string",
       "address?": "string",
       "avatarUrl?": "string",
       "webhook?": {
        "id?": "string",
        "name?": "string",
        "avatar?": "string",
        "url?": "string"
       },
       "metadata?": {
        "allowImages?": "boolean",
        "allowVideos?": "boolean",
        "allowGalleries?": "boolean",
        "linkFlairEnabled?": "boolean",
        "facebookPageId?": "string"
       }
      }
     ],
     "mastodonServerId?": "string",
     "instagramConnectionMethod?": "enum:FACEBOOK|INSTAGRAM",
     "snapchatConnectionMethod?": "enum:PERSONAL|BUSINESS",
     "twitterSubType?": "enum:none|basic|premium|premium_plus",
     "isTiktokBusinessAccount?": "boolean",
     "disconnectedCheckTryAt?": "string",
     "deleteOn?": "string",
     "messagingStatus?": "enum:DISABLED|ENABLED|DISABLE_PENDING",
     "messagingStatusUpdatedAt?": "string",
     "messagingLastError?": "string",
     "createdAt": "string",
     "updatedAt": "string",
     "deletedAt?": "string"
    }
   ],
   "bio?": {
    "id": "string",
    "username": "string",
    "name": "string",
    "description": "string",
    "avatarUrl": "string",
    "socials": {},
    "teamId": "string",
    "createdAt": "string",
    "updatedAt": "string",
    "items": [
     {
      "id": "string",
      "bioId": "string",
      "name": "string",
      "link": "string",
      "icon?": "string",
      "enabled": "boolean",
      "order?": "number",
      "createdAt": "string",
      "updatedAt": "string",
      "analytics": [
       {
        "id": "string",
        "count": "number",
        "bioItemId": "string",
        "deviceType": {},
        "country": {},
        "createdAt": "string",
        "updatedAt": "string"
       }
      ]
     }
    ]
   }
  }
 ],
 "total": "number"
}
```


## GET /api/v1/team/{id} — Get team

Retrieve a single team with its connected social accounts and settings. Teams are the container that social accounts, posts, and uploads belong to.

- param path id: "string"

Response 200:
```json
{
 "id": "string",
 "name": "string",
 "avatarUrl?": "string",
 "organizationId": "string",
 "createdById": "string",
 "createdAt": "string",
 "updatedAt": "string",
 "deletedAt?": "string",
 "organization": {
  "id": "string",
  "createdById": "string",
  "promotionCodeId?": "string",
  "name?": "string",
  "avatarUrl?": "string",
  "ref?": "string",
  "dailyPostLimit?": {
   "TWITTER?": "number",
   "FACEBOOK?": "number",
   "INSTAGRAM?": "number",
   "LINKEDIN?": "number",
   "YOUTUBE?": "number",
   "TIKTOK?": "number",
   "THREADS?": "number",
   "PINTEREST?": "number",
   "REDDIT?": "number",
   "DISCORD?": "number",
   "SLACK?": "number",
   "MASTODON?": "number",
   "BLUESKY?": "number",
   "GOOGLE_BUSINESS?": "number",
   "SNAPCHAT?": "number"
  },
  "dailyCommentLimit?": {
   "TWITTER?": "number",
   "FACEBOOK?": "number",
   "INSTAGRAM?": "number",
   "LINKEDIN?": "number",
   "YOUTUBE?": "number",
   "TIKTOK?": "number",
   "THREADS?": "number",
   "PINTEREST?": "number",
   "REDDIT?": "number",
   "DISCORD?": "number",
   "SLACK?": "number",
   "MASTODON?": "number",
   "BLUESKY?": "number",
   "GOOGLE_BUSINESS?": "number",
   "SNAPCHAT?": "number"
  },
  "monthlyImportLimitPerAccount?": "number",
  "commentImportLimitPerPost?": "number",
  "monthlyReviewImportLimitPerAccount?": "number",
  "monthlyMessageLimitPerAccount?": "number",
  "monthlyAutomationExecutionLimitPerAccount?": "number",
  "apiAccess": "boolean",
  "analyticsDisabled": "boolean",
  "analyticsPostsDisabled": "boolean",
  "uploadsCompressionEnabled": "boolean",
  "analyticsInterval?": "number",
  "analyticsPostsInterval?": "number",
  "forcedAccountAnalyticsDailyLimit?": "number",
  "forcedPostAnalyticsDailyLimit?": "number",
  "showVerboseErrors": "boolean",
  "disconnectCheckEnabled": "boolean",
  "deleteAccountAfter": "integer",
  "createdAt": "string",
  "updatedAt": "string",
  "deletedAt?": "string",
  "suspended?": "boolean"
 },
 "createdBy": {
  "id": "string",
  "externalId": "string",
  "email": "string",
  "emailVerified?": "string",
  "firstName?": "string",
  "lastName?": "string",
  "avatarUrl?": "string",
  "timezone?": "string",
  "role": "enum:ADMIN|CUSTOMER",
  "createdAt": "string",
  "updatedAt": "string",
  "deletedAt?": "string"
 },
 "bots": [
  {
   "id": "string",
   "name": "string",
   "avatarUrl?": "string",
   "teamId": "string",
   "createdAt": "string",
   "updatedAt": "string",
   "deletedAt?": "string"
  }
 ],
 "socialAccounts": [
  {
   "id": "string",
   "type": "enum:TIKTOK|YOUTUBE|INSTAGRAM|FACEBOOK|TWITTER|THREADS|LINKEDIN|PINTEREST|REDDIT|MASTODON|DISCORD|SLACK|BLUESKY|GOOGLE_BUSINESS|SNAPCHAT",
   "teamId": "string",
   "username?": "string",
   "displayName?": "string",
   "bio?": "string",
   "avatarUrl?": "string",
   "externalId?": "string",
   "providerPageId?": "string",
   "userUsername?": "string",
   "userDisplayName?": "string",
   "userEmail?": "string",
   "userId?": "string",
   "channels?": [
    {
     "id": "string",
     "name?": "string",
     "username?": "string",
     "address?": "string",
     "avatarUrl?": "string",
     "webhook?": {
      "id?": "string",
      "name?": "string",
      "avatar?": "string",
      "url?": "string"
     },
     "metadata?": {
      "allowImages?": "boolean",
      "allowVideos?": "boolean",
      "allowGalleries?": "boolean",
      "linkFlairEnabled?": "boolean",
      "facebookPageId?": "string"
     }
    }
   ],
   "mastodonServerId?": "string",
   "instagramConnectionMethod?": "enum:FACEBOOK|INSTAGRAM",
   "snapchatConnectionMethod?": "enum:PERSONAL|BUSINESS",
   "twitterSubType?": "enum:none|basic|premium|premium_plus",
   "isTiktokBusinessAccount?": "boolean",
   "disconnectedCheckTryAt?": "string",
   "deleteOn?": "string",
   "messagingStatus?": "enum:DISABLED|ENABLED|DISABLE_PENDING",
   "messagingStatusUpdatedAt?": "string",
   "messagingLastError?": "string",
   "createdAt": "string",
   "updatedAt": "string",
   "deletedAt?": "string"
  }
 ],
 "bio?": {
  "id": "string",
  "username": "string",
  "name": "string",
  "description": "string",
  "avatarUrl": "string",
  "socials": {},
  "teamId": "string",
  "createdAt": "string",
  "updatedAt": "string",
  "items": [
   {
    "id": "string",
    "bioId": "string",
    "name": "string",
    "link": "string",
    "icon?": "string",
    "enabled": "boolean",
    "order?": "number",
    "createdAt": "string",
    "updatedAt": "string",
    "analytics": [
     {
      "id": "string",
      "count": "number",
      "bioItemId": "string",
      "deviceType": {},
      "country": {},
      "createdAt": "string",
      "updatedAt": "string"
     }
    ]
   }
  ]
 }
}
```


## POST /api/v1/social-account/create-portal-link — Create portal link

Simplify connect flow. Create a portal link which can be used to manage connected social accounts directly on bundle.social platform without implementing the logic on your side.


Request (application/json):
```json
{
 "teamId": "string",
 "redirectUrl?": "string",
 "socialAccountTypes": [
  "enum:TIKTOK|YOUTUBE|INSTAGRAM|FACEBOOK|TWITTER|THREADS|LINKEDIN|PINTEREST|REDDIT|MASTODON|DISCORD|SLACK|BLUESKY|GOOGLE_BUSINESS|SNAPCHAT"
 ],
 "serverUrl?": "string",
 "disableAutoLogin?": "boolean",
 "tiktokForceLogin?": "boolean",
 "forceBrowserOAuth?": "boolean",
 "instagramConnectionMethod?": "enum:FACEBOOK|INSTAGRAM",
 "snapchatConnectionMethod?": "enum:PERSONAL|BUSINESS",
 "withBusinessScope?": "boolean",
 "withMessagingScope?": "boolean",
 "expiresIn?": "integer",
 "logoUrl?": "string",
 "userLogoUrl?": "string",
 "userName?": "string",
 "goBackButtonText?": "string",
 "hidePoweredBy?": "boolean",
 "hideGoBackButton?": "boolean",
 "hideUserLogo?": "boolean",
 "hideUserName?": "boolean",
 "hideLanguageSwitcher?": "boolean",
 "showModalOnConnectSuccess?": "boolean",
 "language?": "enum:en|pl|fr|hi|sv|de|es|it|nl|pt|ru|tr|zh|da|no|th|ko|he|ar",
 "maxSocialAccountsConnected?": "number"
}
```

Response 200:
```json
{
 "url": "string"
}
```


## POST /api/v1/upload/ — Create upload

Upload a file. This is the only endpoint that uses multipart/form-data.


Request (multipart/form-data):
```json
{
 "teamId?": "string",
 "file?": "string"
}
```

Response 200:
```json
{
 "id": "string",
 "teamId?": "string",
 "organizationId?": "string",
 "iconUrl?": "string",
 "thumbnailUrl?": "string",
 "url?": "string",
 "externalLink?": "string",
 "iconPath?": "string",
 "thumbnailPath?": "string",
 "path?": "string",
 "type": "enum:image|video|document",
 "width?": "number",
 "height?": "number",
 "fileSize?": "number",
 "videoLength?": "number",
 "mime?": "string",
 "ext?": "string",
 "createdAt": "string",
 "updatedAt": "string"
}
```


## POST /api/v1/upload/init — Initialize large upload

Initialize large upload, you need to initialize a large upload if your file is larger than 90 MB.


Request (application/json):
```json
{
 "teamId?": "string",
 "fileName": "string",
 "mimeType": "enum:image/jpg|image/jpeg|image/png|image/gif|video/mp4|video/quicktime|application/pdf",
 "fileSize?": "integer"
}
```

Response 200:
```json
{
 "url": "string",
 "path": "string"
}
```


## POST /api/v1/upload/finalize — Finalize large upload

Finalize large upload.


Request (application/json):
```json
{
 "teamId?": "string",
 "path": "string"
}
```

Response 200:
```json
{
 "id": "string",
 "teamId?": "string",
 "organizationId?": "string",
 "iconUrl?": "string",
 "thumbnailUrl?": "string",
 "url?": "string",
 "externalLink?": "string",
 "iconPath?": "string",
 "thumbnailPath?": "string",
 "path?": "string",
 "type": "enum:image|video|document",
 "width?": "number",
 "height?": "number",
 "fileSize?": "number",
 "videoLength?": "number",
 "mime?": "string",
 "ext?": "string",
 "createdAt": "string",
 "updatedAt": "string"
}
```


## GET /api/v1/upload/{id} — Get upload

Retrieve a single media file with its processing status, dimensions, duration, and the posts it is attached to.

- param path id: "string"

Response 200:
```json
{
 "id": "string",
 "teamId?": "string",
 "organizationId?": "string",
 "iconUrl?": "string",
 "thumbnailUrl?": "string",
 "url?": "string",
 "externalLink?": "string",
 "iconPath?": "string",
 "thumbnailPath?": "string",
 "path?": "string",
 "type": "enum:image|video|document",
 "width?": "number",
 "height?": "number",
 "fileSize?": "number",
 "videoLength?": "number",
 "mime?": "string",
 "ext?": "string",
 "createdAt": "string",
 "updatedAt": "string",
 "posts?": [
  {
   "postId": "string",
   "uploadId": "string",
   "createdAt": "string",
   "updatedAt": "string",
   "deletedAt?": "string"
  }
 ]
}
```


## POST /api/v1/post/ — Create post

Schedule or immediately publish a post to one or more connected social accounts in a single request. Supply shared content plus optional per-platform overrides for captions, media, and platform-specific options.


Request (application/json):
```json
{
 "teamId": "string",
 "title": "string",
 "referenceKey?": "string",
 "postDate": "string",
 "status": "enum:DRAFT|SCHEDULED",
 "socialAccountTypes": [
  "enum:TIKTOK|YOUTUBE|INSTAGRAM|FACEBOOK|TWITTER|THREADS|LINKEDIN|PINTEREST|REDDIT|MASTODON|DISCORD|SLACK|BLUESKY|GOOGLE_BUSINESS|SNAPCHAT"
 ],
 "data": {
  "TWITTER?": {
   "text?": "string",
   "uploadIds?": [
    "string"
   ],
   "mediaItems?": [
    {
     "uploadId": "string",
     "altText?": "string"
    }
   ],
   "replySettings?": "enum:EVERYONE|FOLLOWING|MENTIONED_USERS|SUBSCRIBERS|VERIFIED",
   "poll?": {
    "options": [
     "string"
    ],
    "durationMinutes": "integer"
   },
   "quoteTweetId?": "string",
   "replyToTweetId?": "string",
   "subscribersOnly?": "boolean",
   "thread?": [
    {
     "text?": "string",
     "uploadIds?": [
      "string"
     ]
    }
   ],
   "tweetStorm?": "boolean",
   "tweetStormNumbering?": "boolean",
   "isAiGenerated?": "boolean"
  },
  "PINTEREST?": {
   "text?": "string",
   "description?": "string",
   "boardName": "string",
   "uploadIds?": [
    "string"
   ],
   "carouselItems?": [
    {
     "uploadId": "string",
     "title?": "string",
     "description?": "string",
     "link?": "string"
    }
   ],
   "thumbnail?": "string",
   "link?": "string",
   "altText?": "string",
   "note?": "string",
   "dominantColor?": "string",
   "isAiGenerated?": "boolean"
  },
  "FACEBOOK?": {
   "type?": "enum:POST|REEL|STORY",
   "text?": "string",
   "uploadIds?": [
    "string"
   ],
   "mediaItems?": [
    {
     "uploadId": "string",
     "altText?": "string"
    }
   ],
   "link?": "string",
   "thumbnail?": "string",
   "mediaTitle?": "string",
   "nativeScheduleTime?": "string",
   "textFormatPresetId?": "string"
  },
  "INSTAGRAM?": {
   "type?": "enum:POST|REEL|STORY",
   "text?": "string",
   "uploadIds?": [
    "string"
   ],
   "altText?": "string",
   "thumbnailOffset?": "number",
   "thumbnail?": "string",
   "shareToFeed?": "boolean",
   "collaborators?": [
    "string"
   ],
   "autoFitImage?": "boolean",
   "autoCropImage?": "boolean",
   "tagged?": [
    {
     "username": "string",
     "x?": "number",
     "y?": "number"
    }
   ],
   "carouselItems?": [
    {
     "uploadId": "string",
     "altText?": "string",
     "tagged?": [
      {
       "username": "string",
       "x": "number",
       "y": "number"
      }
     ]
    }
   ],
   "locationId?": "string",
   "trialParams?": {
    "graduationStrategy": "enum:MANUAL|SS_PERFORMANCE"
   },
   "isPaidPartnership?": "boolean",
   "brandedContentSponsors?": [
    "string"
   ],
   "musicSoundInfo?": {
    "musicSoundId": "string",
    "musicSoundVolume?": "integer",
    "videoOriginalSoundVolume?": "integer"
   },
   "isAiGenerated?": "boolean"
  },
  "THREADS?": {
   "text?": "string",
   "uploadIds?": [
    "string"
   ],
   "mediaItems?": [
    {
     "uploadId": "string",
     "altText?": "string"
    }
   ],
   "topicTag?": "string",
   "replyControl?": "enum:everyone|accounts_you_follow|mentioned_only|parent_post_author_only|followers_only",
   "linkAttachment?": "string",
   "poll?": {
    "optionA": "string",
    "optionB": "string",
    "optionC?": "string",
    "optionD?": "string"
   },
   "gif?": {
    "gifId": "string",
    "provider?": "enum:GIPHY"
   },
   "allowlistedCountryCodes?": [
    "string"
   ],
   "crosspostToInstagramStory?": "boolean",
   "crosspostToInstagramStoryDarkMode?": "boolean",
   "isGhostPost?": "boolean"
  },
  "TIKTOK?": {
   "type?": "enum:VIDEO|IMAGE",
   "text?": "string",
   "uploadIds?": [
    "string"
   ],
   "thumbnail?": "string",
   "privacy?": "enum:SELF_ONLY|PUBLIC_TO_EVERYONE|MUTUAL_FOLLOW_FRIENDS|FOLLOWER_OF_CREATOR",
   "photoCoverIndex?": "integer",
   "isBrandContent?": "boolean",
   "isOrganicBrandContent?": "boolean",
   "disableComments?": "boolean",
   "disableDuet?": "boolean",
   "disableStitch?": "boolean",
   "thumbnailOffset?": "number",
   "isAiGenerated?": "boolean",
   "autoAddMusic?": "boolean",
   "autoScale?": "boolean",
   "uploadToDraft?": "boolean",
   "musicSoundInfo?": {
    "musicSoundId": "string",
    "musicSoundVolume?": "integer",
    "musicSoundStart?": "integer",
    "musicSoundEnd?": "integer",
    "videoOriginalSoundVolume?": "integer"
   },
   "title?": "string",
   "locationId?": "string",
   "locationName?": "string"
  },
  "LINKEDIN?": {
   "text": "string",
   "uploadIds?": [
    "string"
   ],
   "link?": "string",
   "thumbnail?": "string",
   "mediaTitle?": "string",
   "privacy?": "enum:CONNECTIONS|PUBLIC|LOGGED_IN|CONTAINER",
   "hideFromFeed?": "boolean",
   "disableReshare?": "boolean",
   "poll?": {
    "question": "string",
    "options": [
     "string"
    ],
    "duration?": "enum:ONE_DAY|THREE_DAYS|SEVEN_DAYS|FOURTEEN_DAYS"
   }
  },
  "YOUTUBE?": {
   "type?": "enum:VIDEO|SHORT",
   "uploadIds?": [
    "string"
   ],
   "text?": "string",
   "description?": "string",
   "thumbnail?": "string",
   "privacy?": "enum:PRIVATE|PUBLIC|UNLISTED",
   "defaultLanguage?": "string",
   "defaultAudioLanguage?": "string",
   "madeForKids?": "boolean",
   "containsSyntheticMedia?": "boolean",
   "hasPaidProductPlacement?": "boolean"
  },
  "REDDIT?": {
   "sr": "string",
   "text": "string",
   "description?": "string",
   "uploadIds?": [
    "string"
   ],
   "link?": "string",
   "nsfw?": "boolean",
   "flairId?": "string"
  },
  "DISCORD?": {
   "channelId": "string",
   "text?": "string",
   "uploadIds?": [
    "string"
   ],
   "username?": "string",
   "avatarUrl?": "string"
  },
  "SLACK?": {
   "channelId": "string",
   "text?": "string",
   "uploadIds?": [
    "string"
   ],
   "username?": "string",
   "avatarUrl?": "string"
  },
  "MASTODON?": {
   "text?": "string",
   "uploadIds?": [
    "string"
   ],
   "thumbnail?": "string",
   "privacy?": "enum:PUBLIC|UNLISTED|PRIVATE|DIRECT",
   "spoiler?": "string"
  },
  "BLUESKY?": {
   "text?": "string",
   "uploadIds?": [
    "string"
   ],
   "tags?": [
    "string"
   ],
   "labels?": [
    "enum:!no-unauthenticated|porn|sexual|nudity|graphic-media"
   ],
   "quoteUri?": "string",
   "externalUrl?": "string",
   "externalTitle?": "string",
   "externalDescription?": "string",
   "thumbnail?": "string",
   "videoAlt?": "string"
  },
  "GOOGLE_BUSINESS?": {
   "text?": "string",
   "uploadIds?": [
    "string"
   ],
   "topicType?": "enum:STANDARD|EVENT|OFFER|ALERT",
   "languageCode?": "string",
   "callToActionType?": "enum:BOOK|ORDER|SHOP|LEARN_MORE|SIGN_UP|CALL",
   "callToActionUrl?": "string",
   "eventTitle?": "string",
   "eventStartDate?": "string",
   "eventEndDate?": "string",
   "offerCouponCode?": "string",
   "offerRedeemOnlineUrl?": "string",
   "offerTermsConditions?": "string",
   "alertType?": "enum:COVID_19"
  },
  "SNAPCHAT?": {
   "type?": "enum:STORY|SPOTLIGHT|SAVED_STORY",
   "uploadIds?": [
    "string"
   ],
   "text?": "string",
   "title?": "string",
   "description?": "string",
   "locale?": "string",
   "skipSaveToProfile?": "boolean",
   "storyDuration?": "enum:ONE_DAY|TWO_DAYS|THREE_DAYS|ONE_WEEK"
  }
 },
 "firstComment?": {
  "TIKTOK?": "string",
  "YOUTUBE?": "string",
  "INSTAGRAM?": "string",
  "FACEBOOK?": "string",
  "TWITTER?": "string",
  "THREADS?": "string",
  "LINKEDIN?": "string",
  "REDDIT?": "string",
  "MASTODON?": "string",
  "DISCORD?": "string",
  "SLACK?": "string",
  "BLUESKY?": "string"
 }
}
```

Response 200:
```json
{
 "id": "string",
 "teamId": "string",
 "organizationId?": "string",
 "title": "string",
 "referenceKey?": "string",
 "postDate": "string",
 "postedDate?": "string",
 "status": "enum:DRAFT|SCHEDULED|POSTED|ERROR|DELETED|PROCESSING|REVIEW|RETRYING",
 "data": {
  "TWITTER?": {
   "text?": "string",
   "uploadIds?": [
    "string"
   ],
   "mediaItems?": [
    {
     "uploadId": "string",
     "altText?": "string"
    }
   ],
   "replySettings?": "enum:EVERYONE|FOLLOWING|MENTIONED_USERS|SUBSCRIBERS|VERIFIED",
   "poll?": {
    "options": [
     "string"
    ],
    "durationMinutes": "integer"
   },
   "quoteTweetId?": "string",
   "replyToTweetId?": "string",
   "subscribersOnly?": "boolean",
   "thread?": [
    {
     "text?": "string",
     "uploadIds?": [
      "string"
     ]
    }
   ],
   "tweetStorm?": "boolean",
   "tweetStormNumbering?": "boolean",
   "isAiGenerated?": "boolean"
  },
  "PINTEREST?": {
   "text?": "string",
   "description?": "string",
   "boardName": "string",
   "uploadIds?": [
    "string"
   ],
   "carouselItems?": [
    {
     "uploadId": "string",
     "title?": "string",
     "description?": "string",
     "link?": "string"
    }
   ],
   "thumbnail?": "string",
   "link?": "string",
   "altText?": "string",
   "note?": "string",
   "dominantColor?": "string",
   "isAiGenerated?": "boolean"
  },
  "FACEBOOK?": {
   "type?": "enum:POST|REEL|STORY",
   "text?": "string",
   "uploadIds?": [
    "string"
   ],
   "mediaItems?": [
    {
     "uploadId": "string",
     "altText?": "string"
    }
   ],
   "link?": "string",
   "thumbnail?": "string",
   "mediaTitle?": "string",
   "nativeScheduleTime?": "string",
   "textFormatPresetId?": "string"
  },
  "INSTAGRAM?": {
   "type?": "enum:POST|REEL|STORY",
   "text?": "string",
   "uploadIds?": [
    "string"
   ],
   "altText?": "string",
   "thumbnailOffset?": "number",
   "thumbnail?": "string",
   "shareToFeed?": "boolean",
   "collaborators?": [
    "string"
   ],
   "autoFitImage?": "boolean",
   "autoCropImage?": "boolean",
   "tagged?": [
    {
     "username": "string",
     "x?": "number",
     "y?": "number"
    }
   ],
   "carouselItems?": [
    {
     "uploadId": "string",
     "altText?": "string",
     "tagged?": [
      {
       "username": "string",
       "x": "number",
       "y": "number"
      }
     ]
    }
   ],
   "locationId?": "string",
   "trialParams?": {
    "graduationStrategy": "enum:MANUAL|SS_PERFORMANCE"
   },
   "isPaidPartnership?": "boolean",
   "brandedContentSponsors?": [
    "string"
   ],
   "musicSoundInfo?": {
    "musicSoundId": "string",
    "musicSoundVolume?": "integer",
    "videoOriginalSoundVolume?": "integer"
   },
   "isAiGenerated?": "boolean"
  },
  "THREADS?": {
   "text?": "string",
   "uploadIds?": [
    "string"
   ],
   "mediaItems?": [
    {
     "uploadId": "string",
     "altText?": "string"
    }
   ],
   "topicTag?": "string",
   "replyControl?": "enum:everyone|accounts_you_follow|mentioned_only|parent_post_author_only|followers_only",
   "linkAttachment?": "string",
   "poll?": {
    "optionA": "string",
    "optionB": "string",
    "optionC?": "string",
    "optionD?": "string"
   },
   "gif?": {
    "gifId": "string",
    "provider?": "enum:GIPHY"
   },
   "allowlistedCountryCodes?": [
    "string"
   ],
   "crosspostToInstagramStory?": "boolean",
   "crosspostToInstagramStoryDarkMode?": "boolean",
   "isGhostPost?": "boolean"
  },
  "TIKTOK?": {
   "type?": "enum:VIDEO|IMAGE",
   "text?": "string",
   "uploadIds?": [
    "string"
   ],
   "thumbnail?": "string",
   "privacy?": "enum:SELF_ONLY|PUBLIC_TO_EVERYONE|MUTUAL_FOLLOW_FRIENDS|FOLLOWER_OF_CREATOR",
   "photoCoverIndex?": "integer",
   "isBrandContent?": "boolean",
   "isOrganicBrandContent?": "boolean",
   "disableComments?": "boolean",
   "disableDuet?": "boolean",
   "disableStitch?": "boolean",
   "thumbnailOffset?": "number",
   "isAiGenerated?": "boolean",
   "autoAddMusic?": "boolean",
   "autoScale?": "boolean",
   "uploadToDraft?": "boolean",
   "musicSoundInfo?": {
    "musicSoundId": "string",
    "musicSoundVolume?": "integer",
    "musicSoundStart?": "integer",
    "musicSoundEnd?": "integer",
    "videoOriginalSoundVolume?": "integer"
   },
   "title?": "string",
   "locationId?": "string",
   "locationName?": "string"
  },
  "LINKEDIN?": {
   "text": "string",
   "uploadIds?": [
    "string"
   ],
   "link?": "string",
   "thumbnail?": "string",
   "mediaTitle?": "string",
   "privacy?": "enum:CONNECTIONS|PUBLIC|LOGGED_IN|CONTAINER",
   "hideFromFeed?": "boolean",
   "disableReshare?": "boolean",
   "poll?": {
    "question": "string",
    "options": [
     "string"
    ],
    "duration?": "enum:ONE_DAY|THREE_DAYS|SEVEN_DAYS|FOURTEEN_DAYS"
   }
  },
  "YOUTUBE?": {
   "type?": "enum:VIDEO|SHORT",
   "uploadIds?": [
    "string"
   ],
   "text?": "string",
   "description?": "string",
   "thumbnail?": "string",
   "privacy?": "enum:PRIVATE|PUBLIC|UNLISTED",
   "defaultLanguage?": "string",
   "defaultAudioLanguage?": "string",
   "madeForKids?": "boolean",
   "containsSyntheticMedia?": "boolean",
   "hasPaidProductPlacement?": "boolean"
  },
  "REDDIT?": {
   "sr": "string",
   "text": "string",
   "description?": "string",
   "uploadIds?": [
    "string"
   ],
   "link?": "string",
   "nsfw?": "boolean",
   "flairId?": "string"
  },
  "DISCORD?": {
   "channelId": "string",
   "text?": "string",
   "uploadIds?": [
    "string"
   ],
   "username?": "string",
   "avatarUrl?": "string"
  },
  "SLACK?": {
   "channelId": "string",
   "text?": "string",
   "uploadIds?": [
    "string"
   ],
   "username?": "string",
   "avatarUrl?": "string"
  },
  "MASTODON?": {
   "text?": "string",
   "uploadIds?": [
    "string"
   ],
   "thumbnail?": "string",
   "privacy?": "enum:PUBLIC|UNLISTED|PRIVATE|DIRECT",
   "spoiler?": "string"
  },
  "BLUESKY?": {
   "text?": "string",
   "uploadIds?": [
    "string"
   ],
   "tags?": [
    "string"
   ],
   "labels?": [
    "enum:!no-unauthenticated|po
```


## GET /api/v1/post/ — Get post list

List and filter posts across a team by status, platform, or date range with pagination. Use this to build a content calendar or reconcile your own database with bundle.social.

- param query teamId: "string"
- param query status?: "enum:DRAFT|SCHEDULED|POSTED|ERROR|DELETED|PROCESSING|REVIEW|RETRYING"
- param query orderBy?: "enum:createdAt|updatedAt|postDate|postedDate|deletedAt"
- param query order?: "enum:ASC|DESC"
- param query q?: "string"
- param query platforms?: ["enum:TIKTOK|YOUTUBE|INSTAGRAM|FACEBOOK|TWITTER|THREADS|LINKEDIN|PINTEREST|REDDIT|MASTODON|DISCORD|SLACK|BLUESKY|GOOGLE_BUSINESS|SNAPCHAT"]
- param query postDateFrom?: "string"
- param query postDateTo?: "string"
- param query offset?: "integer"
- param query limit?: "integer"

Response 200:
```json
{
 "items": [
  {
   "id": "string",
   "teamId": "string",
   "organizationId?": "string",
   "title": "string",
   "referenceKey?": "string",
   "postDate": "string",
   "postedDate?": "string",
   "status": "enum:DRAFT|SCHEDULED|POSTED|ERROR|DELETED|PROCESSING|REVIEW|RETRYING",
   "data": {
    "TWITTER?": {
     "text?": "string",
     "uploadIds?": [
      "string"
     ],
     "mediaItems?": [
      {
       "uploadId": "string",
       "altText?": "string"
      }
     ],
     "replySettings?": "enum:EVERYONE|FOLLOWING|MENTIONED_USERS|SUBSCRIBERS|VERIFIED",
     "poll?": {
      "options": [
       "string"
      ],
      "durationMinutes": "integer"
     },
     "quoteTweetId?": "string",
     "replyToTweetId?": "string",
     "subscribersOnly?": "boolean",
     "thread?": [
      {
       "text?": "string",
       "uploadIds?": [
        "string"
       ]
      }
     ],
     "tweetStorm?": "boolean",
     "tweetStormNumbering?": "boolean",
     "isAiGenerated?": "boolean"
    },
    "PINTEREST?": {
     "text?": "string",
     "description?": "string",
     "boardName": "string",
     "uploadIds?": [
      "string"
     ],
     "carouselItems?": [
      {
       "uploadId": "string",
       "title?": "string",
       "description?": "string",
       "link?": "string"
      }
     ],
     "thumbnail?": "string",
     "link?": "string",
     "altText?": "string",
     "note?": "string",
     "dominantColor?": "string",
     "isAiGenerated?": "boolean"
    },
    "FACEBOOK?": {
     "type?": "enum:POST|REEL|STORY",
     "text?": "string",
     "uploadIds?": [
      "string"
     ],
     "mediaItems?": [
      {
       "uploadId": "string",
       "altText?": "string"
      }
     ],
     "link?": "string",
     "thumbnail?": "string",
     "mediaTitle?": "string",
     "nativeScheduleTime?": "string",
     "textFormatPresetId?": "string"
    },
    "INSTAGRAM?": {
     "type?": "enum:POST|REEL|STORY",
     "text?": "string",
     "uploadIds?": [
      "string"
     ],
     "altText?": "string",
     "thumbnailOffset?": "number",
     "thumbnail?": "string",
     "shareToFeed?": "boolean",
     "collaborators?": [
      "string"
     ],
     "autoFitImage?": "boolean",
     "autoCropImage?": "boolean",
     "tagged?": [
      {
       "username": "string",
       "x?": "number",
       "y?": "number"
      }
     ],
     "carouselItems?": [
      {
       "uploadId": "string",
       "altText?": "string",
       "tagged?": [
        {
         "username": "…",
         "x": "…",
         "y": "…"
        }
       ]
      }
     ],
     "locationId?": "string",
     "trialParams?": {
      "graduationStrategy": "enum:MANUAL|SS_PERFORMANCE"
     },
     "isPaidPartnership?": "boolean",
     "brandedContentSponsors?": [
      "string"
     ],
     "musicSoundInfo?": {
      "musicSoundId": "string",
      "musicSoundVolume?": "integer",
      "videoOriginalSoundVolume?": "integer"
     },
     "isAiGenerated?": "boolean"
    },
    "THREADS?": {
     "text?": "string",
     "uploadIds?": [
      "string"
     ],
     "mediaItems?": [
      {
       "uploadId": "string",
       "altText?": "string"
      }
     ],
     "topicTag?": "string",
     "replyControl?": "enum:everyone|accounts_you_follow|mentioned_only|parent_post_author_only|followers_only",
     "linkAttachment?": "string",
     "poll?": {
      "optionA": "string",
      "optionB": "string",
      "optionC?": "string",
      "optionD?": "string"
     },
     "gif?": {
      "gifId": "string",
      "provider?": "enum:GIPHY"
     },
     "allowlistedCountryCodes?": [
      "string"
     ],
     "crosspostToInstagramStory?": "boolean",
     "crosspostToInstagramStoryDarkMode?": "boolean",
     "isGhostPost?": "boolean"
    },
    "TIKTOK?": {
     "type?": "enum:VIDEO|IMAGE",
     "text?": "string",
     "uploadIds?": [
      "string"
     ],
     "thumbnail?": "string",
     "privacy?": "enum:SELF_ONLY|PUBLIC_TO_EVERYONE|MUTUAL_FOLLOW_FRIENDS|FOLLOWER_OF_CREATOR",
     "photoCoverIndex?": "integer",
     "isBrandContent?": "boolean",
     "isOrganicBrandContent?": "boolean",
     "disableComments?": "boolean",
     "disableDuet?": "boolean",
     "disableStitch?": "boolean",
     "thumbnailOffset?": "number",
     "isAiGenerated?": "boolean",
     "autoAddMusic?": "boolean",
     "autoScale?": "boolean",
     "uploadToDraft?": "boolean",
     "musicSoundInfo?": {
      "musicSoundId": "string",
      "musicSoundVolume?": "integer",
      "musicSoundStart?": "integer",
      "musicSoundEnd?": "integer",
      "videoOriginalSoundVolume?": "integer"
     },
     "title?": "string",
     "locationId?": "string",
     "locationName?": "string"
    },
    "LINKEDIN?": {
     "text": "string",
     "uploadIds?": [
      "string"
     ],
     "link?": "string",
     "thumbnail?": "string",
     "mediaTitle?": "string",
     "privacy?": "enum:CONNECTIONS|PUBLIC|LOGGED_IN|CONTAINER",
     "hideFromFeed?": "boolean",
     "disableReshare?": "boolean",
     "poll?": {
      "question": "string",
      "options": [
       "string"
      ],
      "duration?": "enum:ONE_DAY|THREE_DAYS|SEVEN_DAYS|FOURTEEN_DAYS"
     }
    },
    "YOUTUBE?": {
     "type?": "enum:VIDEO|SHORT",
     "uploadIds?": [
      "string"
     ],
     "text?": "string",
     "description?": "string",
     "thumbnail?": "string",
     "privacy?": "enum:PRIVATE|PUBLIC|UNLISTED",
     "defaultLanguage?": "string",
     "defaultAudioLanguage?": "string",
     "madeForKids?": "boolean",
     "containsSyntheticMedia?": "boolean",
     "hasPaidProductPlacement?": "boolean"
    },
    "REDDIT?": {
     "sr": "string",
     "text": "string",
     "description?": "string",
     "uploadIds?": [
      "string"
     ],
     "link?": "string",
     "nsfw?": "boolean",
     "flairId?": "string"
    },
    "DISCORD?": {
     "channelId": "string",
     "text?": "string",
     "uploadIds?": [
      "string"
     ],
     "username?": "string",
     "avatarUrl?": "string"
    },
    "S
```


## GET /api/v1/post/{id} — Get post

Retrieve a single post by ID, including its per-platform status, scheduled time, media, and any publishing errors.

- param path id: "string"

Response 200:
```json
{
 "id": "string",
 "teamId": "string",
 "organizationId?": "string",
 "title": "string",
 "referenceKey?": "string",
 "postDate": "string",
 "postedDate?": "string",
 "status": "enum:DRAFT|SCHEDULED|POSTED|ERROR|DELETED|PROCESSING|REVIEW|RETRYING",
 "data": {
  "TWITTER?": {
   "text?": "string",
   "uploadIds?": [
    "string"
   ],
   "mediaItems?": [
    {
     "uploadId": "string",
     "altText?": "string"
    }
   ],
   "replySettings?": "enum:EVERYONE|FOLLOWING|MENTIONED_USERS|SUBSCRIBERS|VERIFIED",
   "poll?": {
    "options": [
     "string"
    ],
    "durationMinutes": "integer"
   },
   "quoteTweetId?": "string",
   "replyToTweetId?": "string",
   "subscribersOnly?": "boolean",
   "thread?": [
    {
     "text?": "string",
     "uploadIds?": [
      "string"
     ]
    }
   ],
   "tweetStorm?": "boolean",
   "tweetStormNumbering?": "boolean",
   "isAiGenerated?": "boolean"
  },
  "PINTEREST?": {
   "text?": "string",
   "description?": "string",
   "boardName": "string",
   "uploadIds?": [
    "string"
   ],
   "carouselItems?": [
    {
     "uploadId": "string",
     "title?": "string",
     "description?": "string",
     "link?": "string"
    }
   ],
   "thumbnail?": "string",
   "link?": "string",
   "altText?": "string",
   "note?": "string",
   "dominantColor?": "string",
   "isAiGenerated?": "boolean"
  },
  "FACEBOOK?": {
   "type?": "enum:POST|REEL|STORY",
   "text?": "string",
   "uploadIds?": [
    "string"
   ],
   "mediaItems?": [
    {
     "uploadId": "string",
     "altText?": "string"
    }
   ],
   "link?": "string",
   "thumbnail?": "string",
   "mediaTitle?": "string",
   "nativeScheduleTime?": "string",
   "textFormatPresetId?": "string"
  },
  "INSTAGRAM?": {
   "type?": "enum:POST|REEL|STORY",
   "text?": "string",
   "uploadIds?": [
    "string"
   ],
   "altText?": "string",
   "thumbnailOffset?": "number",
   "thumbnail?": "string",
   "shareToFeed?": "boolean",
   "collaborators?": [
    "string"
   ],
   "autoFitImage?": "boolean",
   "autoCropImage?": "boolean",
   "tagged?": [
    {
     "username": "string",
     "x?": "number",
     "y?": "number"
    }
   ],
   "carouselItems?": [
    {
     "uploadId": "string",
     "altText?": "string",
     "tagged?": [
      {
       "username": "string",
       "x": "number",
       "y": "number"
      }
     ]
    }
   ],
   "locationId?": "string",
   "trialParams?": {
    "graduationStrategy": "enum:MANUAL|SS_PERFORMANCE"
   },
   "isPaidPartnership?": "boolean",
   "brandedContentSponsors?": [
    "string"
   ],
   "musicSoundInfo?": {
    "musicSoundId": "string",
    "musicSoundVolume?": "integer",
    "videoOriginalSoundVolume?": "integer"
   },
   "isAiGenerated?": "boolean"
  },
  "THREADS?": {
   "text?": "string",
   "uploadIds?": [
    "string"
   ],
   "mediaItems?": [
    {
     "uploadId": "string",
     "altText?": "string"
    }
   ],
   "topicTag?": "string",
   "replyControl?": "enum:everyone|accounts_you_follow|mentioned_only|parent_post_author_only|followers_only",
   "linkAttachment?": "string",
   "poll?": {
    "optionA": "string",
    "optionB": "string",
    "optionC?": "string",
    "optionD?": "string"
   },
   "gif?": {
    "gifId": "string",
    "provider?": "enum:GIPHY"
   },
   "allowlistedCountryCodes?": [
    "string"
   ],
   "crosspostToInstagramStory?": "boolean",
   "crosspostToInstagramStoryDarkMode?": "boolean",
   "isGhostPost?": "boolean"
  },
  "TIKTOK?": {
   "type?": "enum:VIDEO|IMAGE",
   "text?": "string",
   "uploadIds?": [
    "string"
   ],
   "thumbnail?": "string",
   "privacy?": "enum:SELF_ONLY|PUBLIC_TO_EVERYONE|MUTUAL_FOLLOW_FRIENDS|FOLLOWER_OF_CREATOR",
   "photoCoverIndex?": "integer",
   "isBrandContent?": "boolean",
   "isOrganicBrandContent?": "boolean",
   "disableComments?": "boolean",
   "disableDuet?": "boolean",
   "disableStitch?": "boolean",
   "thumbnailOffset?": "number",
   "isAiGenerated?": "boolean",
   "autoAddMusic?": "boolean",
   "autoScale?": "boolean",
   "uploadToDraft?": "boolean",
   "musicSoundInfo?": {
    "musicSoundId": "string",
    "musicSoundVolume?": "integer",
    "musicSoundStart?": "integer",
    "musicSoundEnd?": "integer",
    "videoOriginalSoundVolume?": "integer"
   },
   "title?": "string",
   "locationId?": "string",
   "locationName?": "string"
  },
  "LINKEDIN?": {
   "text": "string",
   "uploadIds?": [
    "string"
   ],
   "link?": "string",
   "thumbnail?": "string",
   "mediaTitle?": "string",
   "privacy?": "enum:CONNECTIONS|PUBLIC|LOGGED_IN|CONTAINER",
   "hideFromFeed?": "boolean",
   "disableReshare?": "boolean",
   "poll?": {
    "question": "string",
    "options": [
     "string"
    ],
    "duration?": "enum:ONE_DAY|THREE_DAYS|SEVEN_DAYS|FOURTEEN_DAYS"
   }
  },
  "YOUTUBE?": {
   "type?": "enum:VIDEO|SHORT",
   "uploadIds?": [
    "string"
   ],
   "text?": "string",
   "description?": "string",
   "thumbnail?": "string",
   "privacy?": "enum:PRIVATE|PUBLIC|UNLISTED",
   "defaultLanguage?": "string",
   "defaultAudioLanguage?": "string",
   "madeForKids?": "boolean",
   "containsSyntheticMedia?": "boolean",
   "hasPaidProductPlacement?": "boolean"
  },
  "REDDIT?": {
   "sr": "string",
   "text": "string",
   "description?": "string",
   "uploadIds?": [
    "string"
   ],
   "link?": "string",
   "nsfw?": "boolean",
   "flairId?": "string"
  },
  "DISCORD?": {
   "channelId": "string",
   "text?": "string",
   "uploadIds?": [
    "string"
   ],
   "username?": "string",
   "avatarUrl?": "string"
  },
  "SLACK?": {
   "channelId": "string",
   "text?": "string",
   "uploadIds?": [
    "string"
   ],
   "username?": "string",
   "avatarUrl?": "string"
  },
  "MASTODON?": {
   "text?": "string",
   "uploadIds?": [
    "string"
   ],
   "thumbnail?": "string",
   "privacy?": "enum:PUBLIC|UNLISTED|PRIVATE|DIRECT",
   "spoiler?": "string"
  },
  "BLUESKY?": {
   "text?": "string",
   "uploadIds?": [
    "string"
   ],
   "tags?": [
    "string"
   ],
   "labels?": [
    "enum:!no-unauthenticated|po
```


## POST /api/v1/post/{id}/retry — Retry post

Re-attempt publishing a post that failed, for example after a token expired or a platform outage. Fix the underlying cause first, then retry.

- param path id: "string"

Response 200:
```json
{
 "id": "string",
 "teamId": "string",
 "organizationId?": "string",
 "title": "string",
 "referenceKey?": "string",
 "postDate": "string",
 "postedDate?": "string",
 "status": "enum:DRAFT|SCHEDULED|POSTED|ERROR|DELETED|PROCESSING|REVIEW|RETRYING",
 "data": {
  "TWITTER?": {
   "text?": "string",
   "uploadIds?": [
    "string"
   ],
   "mediaItems?": [
    {
     "uploadId": "string",
     "altText?": "string"
    }
   ],
   "replySettings?": "enum:EVERYONE|FOLLOWING|MENTIONED_USERS|SUBSCRIBERS|VERIFIED",
   "poll?": {
    "options": [
     "string"
    ],
    "durationMinutes": "integer"
   },
   "quoteTweetId?": "string",
   "replyToTweetId?": "string",
   "subscribersOnly?": "boolean",
   "thread?": [
    {
     "text?": "string",
     "uploadIds?": [
      "string"
     ]
    }
   ],
   "tweetStorm?": "boolean",
   "tweetStormNumbering?": "boolean",
   "isAiGenerated?": "boolean"
  },
  "PINTEREST?": {
   "text?": "string",
   "description?": "string",
   "boardName": "string",
   "uploadIds?": [
    "string"
   ],
   "carouselItems?": [
    {
     "uploadId": "string",
     "title?": "string",
     "description?": "string",
     "link?": "string"
    }
   ],
   "thumbnail?": "string",
   "link?": "string",
   "altText?": "string",
   "note?": "string",
   "dominantColor?": "string",
   "isAiGenerated?": "boolean"
  },
  "FACEBOOK?": {
   "type?": "enum:POST|REEL|STORY",
   "text?": "string",
   "uploadIds?": [
    "string"
   ],
   "mediaItems?": [
    {
     "uploadId": "string",
     "altText?": "string"
    }
   ],
   "link?": "string",
   "thumbnail?": "string",
   "mediaTitle?": "string",
   "nativeScheduleTime?": "string",
   "textFormatPresetId?": "string"
  },
  "INSTAGRAM?": {
   "type?": "enum:POST|REEL|STORY",
   "text?": "string",
   "uploadIds?": [
    "string"
   ],
   "altText?": "string",
   "thumbnailOffset?": "number",
   "thumbnail?": "string",
   "shareToFeed?": "boolean",
   "collaborators?": [
    "string"
   ],
   "autoFitImage?": "boolean",
   "autoCropImage?": "boolean",
   "tagged?": [
    {
     "username": "string",
     "x?": "number",
     "y?": "number"
    }
   ],
   "carouselItems?": [
    {
     "uploadId": "string",
     "altText?": "string",
     "tagged?": [
      {
       "username": "string",
       "x": "number",
       "y": "number"
      }
     ]
    }
   ],
   "locationId?": "string",
   "trialParams?": {
    "graduationStrategy": "enum:MANUAL|SS_PERFORMANCE"
   },
   "isPaidPartnership?": "boolean",
   "brandedContentSponsors?": [
    "string"
   ],
   "musicSoundInfo?": {
    "musicSoundId": "string",
    "musicSoundVolume?": "integer",
    "videoOriginalSoundVolume?": "integer"
   },
   "isAiGenerated?": "boolean"
  },
  "THREADS?": {
   "text?": "string",
   "uploadIds?": [
    "string"
   ],
   "mediaItems?": [
    {
     "uploadId": "string",
     "altText?": "string"
    }
   ],
   "topicTag?": "string",
   "replyControl?": "enum:everyone|accounts_you_follow|mentioned_only|parent_post_author_only|followers_only",
   "linkAttachment?": "string",
   "poll?": {
    "optionA": "string",
    "optionB": "string",
    "optionC?": "string",
    "optionD?": "string"
   },
   "gif?": {
    "gifId": "string",
    "provider?": "enum:GIPHY"
   },
   "allowlistedCountryCodes?": [
    "string"
   ],
   "crosspostToInstagramStory?": "boolean",
   "crosspostToInstagramStoryDarkMode?": "boolean",
   "isGhostPost?": "boolean"
  },
  "TIKTOK?": {
   "type?": "enum:VIDEO|IMAGE",
   "text?": "string",
   "uploadIds?": [
    "string"
   ],
   "thumbnail?": "string",
   "privacy?": "enum:SELF_ONLY|PUBLIC_TO_EVERYONE|MUTUAL_FOLLOW_FRIENDS|FOLLOWER_OF_CREATOR",
   "photoCoverIndex?": "integer",
   "isBrandContent?": "boolean",
   "isOrganicBrandContent?": "boolean",
   "disableComments?": "boolean",
   "disableDuet?": "boolean",
   "disableStitch?": "boolean",
   "thumbnailOffset?": "number",
   "isAiGenerated?": "boolean",
   "autoAddMusic?": "boolean",
   "autoScale?": "boolean",
   "uploadToDraft?": "boolean",
   "musicSoundInfo?": {
    "musicSoundId": "string",
    "musicSoundVolume?": "integer",
    "musicSoundStart?": "integer",
    "musicSoundEnd?": "integer",
    "videoOriginalSoundVolume?": "integer"
   },
   "title?": "string",
   "locationId?": "string",
   "locationName?": "string"
  },
  "LINKEDIN?": {
   "text": "string",
   "uploadIds?": [
    "string"
   ],
   "link?": "string",
   "thumbnail?": "string",
   "mediaTitle?": "string",
   "privacy?": "enum:CONNECTIONS|PUBLIC|LOGGED_IN|CONTAINER",
   "hideFromFeed?": "boolean",
   "disableReshare?": "boolean",
   "poll?": {
    "question": "string",
    "options": [
     "string"
    ],
    "duration?": "enum:ONE_DAY|THREE_DAYS|SEVEN_DAYS|FOURTEEN_DAYS"
   }
  },
  "YOUTUBE?": {
   "type?": "enum:VIDEO|SHORT",
   "uploadIds?": [
    "string"
   ],
   "text?": "string",
   "description?": "string",
   "thumbnail?": "string",
   "privacy?": "enum:PRIVATE|PUBLIC|UNLISTED",
   "defaultLanguage?": "string",
   "defaultAudioLanguage?": "string",
   "madeForKids?": "boolean",
   "containsSyntheticMedia?": "boolean",
   "hasPaidProductPlacement?": "boolean"
  },
  "REDDIT?": {
   "sr": "string",
   "text": "string",
   "description?": "string",
   "uploadIds?": [
    "string"
   ],
   "link?": "string",
   "nsfw?": "boolean",
   "flairId?": "string"
  },
  "DISCORD?": {
   "channelId": "string",
   "text?": "string",
   "uploadIds?": [
    "string"
   ],
   "username?": "string",
   "avatarUrl?": "string"
  },
  "SLACK?": {
   "channelId": "string",
   "text?": "string",
   "uploadIds?": [
    "string"
   ],
   "username?": "string",
   "avatarUrl?": "string"
  },
  "MASTODON?": {
   "text?": "string",
   "uploadIds?": [
    "string"
   ],
   "thumbnail?": "string",
   "privacy?": "enum:PUBLIC|UNLISTED|PRIVATE|DIRECT",
   "spoiler?": "string"
  },
  "BLUESKY?": {
   "text?": "string",
   "uploadIds?": [
    "string"
   ],
   "tags?": [
    "string"
   ],
   "labels?": [
    "enum:!no-unauthenticated|po
```


## GET /api/v1/misc/tiktok/post-settings — Get the posting options of a TikTok account

Returns the privacy levels, interaction settings (comments, duet, stitch) and maximum video duration the connected TikTok account allows, read live from TikTok. A value the account does not allow is not rejected when you create the post, it fails at publish time with TT:40002. Use it to build the options of your own composer, not as a check before every publish: each call counts against the account's TikTok rate limit.

- param query teamId: "string"

Response 200:
```json
{
 "privacyLevelOptions": [
  "enum:SELF_ONLY|PUBLIC_TO_EVERYONE|MUTUAL_FOLLOW_FRIENDS|FOLLOWER_OF_CREATOR"
 ],
 "commentDisabled": "boolean",
 "duetDisabled": "boolean",
 "stitchDisabled": "boolean",
 "maxVideoPostDurationSec?": "number"
}
```

