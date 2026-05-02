export const PROVIDERS = [
    {
        slug: 'icloud',
        authFlow: 'app_password',
        category: 'Email & Calendar',
        title: 'iCloud',
        description: 'Email and calendar',
        icon: 'bi-envelope-at',
        vendor: 'Apple',
        appPasswordUrl: 'https://account.apple.com/account/manage',
        appPasswordHost: 'account.apple.com',
        emailPlaceholder: 'you@icloud.com',
    },
    {
        slug: 'gmail',
        authFlow: 'app_password',
        category: 'Email & Calendar',
        title: 'Gmail',
        description: 'Email',
        icon: 'bi-envelope-at',
        vendor: 'Google',
        appPasswordUrl: 'https://myaccount.google.com/apppasswords',
        appPasswordHost: 'myaccount.google.com',
        emailPlaceholder: 'you@gmail.com',
    },
    {
        slug: 'google_workspace',
        authFlow: 'oauth_device',
        category: 'Productivity Suites',
        title: 'Google Workspace',
        description: 'Mail, Calendar, Drive, Contacts',
        icon: 'bi-google',
        vendor: 'Google',
        capabilityGroups: [
            {
                id: 'gmail_read',
                label: 'Gmail (read)',
                description: 'Search, list, and read messages',
                scopes: ['https://www.googleapis.com/auth/gmail.readonly'],
                defaultChecked: true,
            },
            {
                id: 'calendar_read',
                label: 'Calendar (read)',
                description: 'List calendars and events',
                scopes: ['https://www.googleapis.com/auth/calendar.readonly'],
                defaultChecked: true,
            },
            {
                id: 'drive_read',
                label: 'Drive (read)',
                description: 'List, search, and read files',
                scopes: ['https://www.googleapis.com/auth/drive.readonly'],
                defaultChecked: true,
            },
            {
                id: 'contacts_read',
                label: 'Contacts (read)',
                description: 'Look up names, emails, phone numbers',
                scopes: ['https://www.googleapis.com/auth/contacts.readonly'],
                defaultChecked: true,
            },
        ],
        baseScopes: ['openid', 'email', 'profile'],
    },
];

export function errorCopy(error, provider) {
    const vendor = provider?.vendor ?? provider?.title ?? 'this provider';
    const isOauth = provider?.authFlow === 'oauth_device';
    switch (error?.code) {
        case 'AUTH':
            if (isOauth) {
                return {
                    title: `${vendor} rejected the OAuth client`,
                    description:
                        'Double-check the Client ID and Client Secret you pasted. '
                        + 'Other common causes: the OAuth client type isn\'t "Desktop app", '
                        + 'or the app hasn\'t been published '
                        + '(Google Auth Platform → Audience → Publish app).',
                };
            }
            return {
                title: `${vendor} rejected the password`,
                description:
                    'App-specific passwords sometimes get revoked or mistyped. ' +
                    `Generate a fresh one in ${vendor}, paste it again, and retry.`,
            };
        case 'UPSTREAM':
            return {
                title: `Couldn't reach ${vendor}`,
                description:
                    'The server returned an error or timed out. Try again in a moment — ' +
                    'if it keeps failing, check your network or the provider\'s status page.',
            };
        case 'BAD_REQUEST':
            return {
                title: 'Couldn\'t add this integration',
                description: error.message || 'The request was rejected. Double-check your inputs.',
            };
        case 'NETWORK':
            return {
                title: 'Network error',
                description: error.message || 'Check your connection and try again.',
            };
        default:
            return {
                title: 'Couldn\'t add this integration',
                description: error?.message || 'Try again, or refresh and start over.',
            };
    }
}

export function slugifyEmail(email) {
    if (!email) return '';
    const local = email.split('@')[0].toLowerCase();
    return local.replace(/[^a-z0-9_-]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 48);
}
