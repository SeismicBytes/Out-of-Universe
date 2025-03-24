import streamlit as st
import pandas as pd
import os

# Function to read a file (supports both CSV and Excel)
def read_file(file):
    try:
        if file.name.endswith('.csv'):
            return pd.read_csv(file)
        elif file.name.endswith('.xlsx'):
            return pd.read_excel(file)
        else:
            raise ValueError("Unsupported file format. Please upload a CSV or Excel file.")
    except Exception as e:
        raise ValueError(f"Error reading file: {str(e)}")

# Function to validate the data file
def validate_data_file(df, revenue_ranges):
    required_columns = ['responseid', 'Country', 'Industry', 'Revenue Range']
    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        raise ValueError(f"Data file is missing required columns: {', '.join(missing_columns)}")
    
    # Validate Revenue Range values
    invalid_revenue_ranges = df['Revenue Range'].dropna().unique()
    invalid_revenue_ranges = [r for r in invalid_revenue_ranges if r not in revenue_ranges]
    if invalid_revenue_ranges:
        raise ValueError(f"Data file contains invalid Revenue Range values: {', '.join(invalid_revenue_ranges)}. Expected values are: {', '.join(revenue_ranges)}")

# Function to validate the universe file
def validate_universe_file(df):
    required_columns = ['Industry', 'Country']
    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        raise ValueError(f"Universe file is missing required columns: {', '.join(missing_columns)}")
    
    # Identify revenue range columns (all columns except 'Industry' and 'Country')
    revenue_ranges = [col for col in df.columns if col not in ['Industry', 'Country']]
    if not revenue_ranges:
        raise ValueError("Universe file must have at least one revenue range column (e.g., 'Less than 250M', '250M to 500M').")
    
    # Validate that revenue range columns are numeric
    for col in revenue_ranges:
        if not pd.api.types.is_numeric_dtype(df[col]):
            raise ValueError(f"Universe file column '{col}' must contain numeric values.")
    
    return revenue_ranges

# Function to find excess respondents and quota fulfillment stats
def process_files(data_df, universe_df, revenue_ranges):
    try:
        # Step 1: Group the data file
        grouped_data = data_df.groupby(['Country', 'Industry', 'Revenue Range']).agg(
            count=('responseid', 'size'),
            response_ids=('responseid', lambda x: sorted(list(x)))
        ).reset_index()

        # Step 2: Reshape the universe file
        universe_df_melted = universe_df.melt(
            id_vars=['Country', 'Industry'],
            value_vars=revenue_ranges,
            var_name='Revenue Range',
            value_name='quota'
        )

        # Step 3: Merge the grouped data with the universe file
        merged_df = grouped_data.merge(
            universe_df_melted,
            on=['Country', 'Industry', 'Revenue Range'],
            how='left'
        )

        # Step 4: Calculate excess and fulfillment percentage
        merged_df['excess'] = merged_df['count'] - merged_df['quota']
        merged_df['excess'] = merged_df['excess'].clip(lower=0)  # Excess cannot be negative
        merged_df['fulfillment_percentage'] = (merged_df['count'] / merged_df['quota'] * 100).clip(upper=100)

        # Step 5: Identify excess respondents
        excess_respondents = []
        for _, row in merged_df.iterrows():
            if row['excess'] > 0:
                excess_ids = row['response_ids'][-int(row['excess']):]
                for resp_id in excess_ids:
                    excess_respondents.append({
                        'Country': row['Country'],
                        'Industry': row['Industry'],
                        'Revenue Range': row['Revenue Range'],
                        'Quota': row['quota'],
                        'Count': row['count'],
                        'Excess': row['excess'],
                        'Response ID': resp_id
                    })

        # Step 6: Prepare quota fulfillment stats
        # Filter out groups with NaN quotas (i.e., groups not in the universe file)
        fulfillment_df = merged_df[merged_df['quota'].notna()].copy()
        fulfillment_df['fulfillment_percentage'] = fulfillment_df['fulfillment_percentage'].round(2)
        # Sort by fulfillment percentage (descending: closest to completion to furthest)
        fulfillment_df = fulfillment_df.sort_values(
            by='fulfillment_percentage',
            ascending=False
        )

        # Ensure the columns exist before selecting
        required_columns = ['Country', 'Industry', 'Revenue Range', 'count', 'quota', 'fulfillment_percentage']
        missing_columns = [col for col in required_columns if col not in fulfillment_df.columns]
        if missing_columns:
            raise ValueError(f"Internal error: Missing columns in fulfillment DataFrame: {', '.join(missing_columns)}")

        # Select columns and rename for display
        fulfillment_df = fulfillment_df[required_columns].rename(columns={
            'count': 'Count',
            'quota': 'Quota',
            'fulfillment_percentage': 'Fulfillment Percentage (%)'
        })

        return excess_respondents, fulfillment_df

    except Exception as e:
        raise ValueError(f"Error processing files: {str(e)}")

# Streamlit app
def main():
    st.title("Quota Excess Respondent Finder")

    # File format instructions
    st.header("File Format Instructions")
    st.markdown("""
    ### Data File
    The data file should contain the following columns:
    - **responseid**: A unique identifier for each respondent (e.g., 11035).
    - **Country**: The country of the respondent (e.g., "South Korea", "Germany").
    - **Industry**: The industry of the respondent (e.g., "Technology/IT", "Retail/FMCG").
    - **Revenue Range**: The revenue range of the respondent (must match the revenue range column names in the universe file).

    **Example:**
    | responseid | Country     | Industry                                      | Revenue Range     |
    |------------|-------------|-----------------------------------------------|-------------------|
    | 11035      | South Korea | Technology/IT                                 | 1B+               |
    | 11033      | Germany     | Retail/FMCG                                   | 250M to 500M      |

    ### Universe File
    The universe file should contain the following columns:
    - **Industry**: The industry (e.g., "Technology/IT", "Retail/FMCG").
    - **Country**: The country (e.g., "South Korea", "Germany").
    - **Revenue Range Columns**: One or more columns representing revenue ranges (e.g., "Less than 250M", "250M to 500M", "500M to 1B", "1B+"). These column names must match the values in the `Revenue Range` column of the data file. The values in these columns should be numeric quotas.

    **Example:**
    | Industry                                      | Country | Less than 250M | 250M to 500M | 500M to 1B | 1B+ |
    |-----------------------------------------------|---------|----------------|--------------|------------|-----|
    | Agriculture, Food (including food production) and Forestry | USA     | 67531          | 363          | 290        | 462 |
    | Technology/IT                                 | Canada  | 6375           | 224          | 175        | 279 |

    **Notes:**
    - Column names are case-sensitive.
    - Country and Industry names must match between the data file and universe file.
    - The `Revenue Range` values in the data file must exactly match the revenue range column names in the universe file.
    """)

    # File upload section
    st.header("Upload Files")
    data_file = st.file_uploader("Upload Data File (CSV or Excel)", type=['csv', 'xlsx'])
    universe_file = st.file_uploader("Upload Universe File (CSV or Excel)", type=['csv', 'xlsx'])

    if data_file and universe_file:
        try:
            # Read the files
            with st.spinner("Reading files..."):
                data_df = read_file(data_file)
                universe_df = read_file(universe_file)

            # Validate the universe file and get revenue ranges
            with st.spinner("Validating files..."):
                revenue_ranges = validate_universe_file(universe_df)
                validate_data_file(data_df, revenue_ranges)

            # Process the files
            with st.spinner("Processing files..."):
                excess_respondents, fulfillment_df = process_files(data_df, universe_df, revenue_ranges)

            # Display results
            st.header("Results")

            # Excess Respondents
            st.subheader("Excess Respondents")
            if excess_respondents:
                excess_df = pd.DataFrame(excess_respondents)
                st.dataframe(excess_df)
                # Download button
                csv = excess_df.to_csv(index=False)
                st.download_button(
                    label="Download Excess Respondents as CSV",
                    data=csv,
                    file_name="excess_respondents.csv",
                    mime="text/csv"
                )
            else:
                st.info("No excess respondents found. All counts are within quotas.")

            # Quota Fulfillment Stats
            st.subheader("Quota Fulfillment Statistics")
            st.markdown("This table shows how much each quota is filled, sorted from closest to completion (100%) to furthest from completion (0%).")
            st.dataframe(fulfillment_df)
            # Download button
            csv = fulfillment_df.to_csv(index=False)
            st.download_button(
                label="Download Quota Fulfillment Stats as CSV",
                data=csv,
                file_name="quota_fulfillment_stats.csv",
                mime="text/csv"
            )

        except ValueError as e:
            st.error(f"Error: {str(e)}")
        except Exception as e:
            st.error(f"An unexpected error occurred: {str(e)}")

if __name__ == "__main__":
    main()
